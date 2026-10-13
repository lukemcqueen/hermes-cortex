//! The local cache — a real SQLite database, compiled into the binary.
//!
//! CHOSEN AFTER MEASURING, not by habit. The first version shelled out to the `sqlite3` CLI to
//! avoid a C dependency; on this host that CLI is ABSENT, so the cache reported itself DISABLED.
//! A search tool whose offline half is silently unavailable is the worst failure mode it has —
//! it is indistinguishable from "nothing found" — and the fallback would have been invisible
//! until an agent needed it. `rusqlite` with the `bundled` feature compiles SQLite IN: the cache
//! works on every host with no external binary and no interpreter to discover.
//!
//! The cost is real and paid at BUILD time: one C compile (the crate cache must be warm, or the
//! network reachable once) and a slightly larger binary. Per query it is cheaper than a
//! subprocess, and there is nothing to install on a host that has neither `sqlite3` nor Python.

use rusqlite::{params, Connection};
use std::path::PathBuf;

/// Where the cache lives: XDG cache home, so Linux and macOS both get a sane location.
pub fn default_path() -> PathBuf {
    let base = std::env::var("XDG_CACHE_HOME")
        .map(PathBuf::from)
        .or_else(|_| std::env::var("HOME").map(|h| PathBuf::from(h).join(".cache")))
        .unwrap_or_else(|_| PathBuf::from("."));
    base.join("fleet-search").join("cache.sqlite3")
}

/// One row of the local corpus.
#[derive(Debug, Clone, PartialEq)]
pub struct Page {
    pub url: String,
    pub title: String,
    pub text: String,
}

pub struct Cache {
    path: PathBuf,
    /// `None` when the database could not be opened — every call then reports WHY, rather than
    /// pretending the corpus is empty.
    conn: Option<Connection>,
    reason: Option<String>,
}

impl Cache {
    pub fn open(path: PathBuf) -> Self {
        if let Some(parent) = path.parent() {
            if let Err(e) = std::fs::create_dir_all(parent) {
                let reason = format!("could not create {}: {e}", parent.display());
                return Cache {
                    path,
                    conn: None,
                    reason: Some(reason),
                };
            }
        }
        match Connection::open(&path) {
            Ok(conn) => {
                let cache = Cache {
                    path,
                    conn: Some(conn),
                    reason: None,
                };
                cache.init();
                cache
            }
            Err(e) => Cache {
                path,
                conn: None,
                reason: Some(format!("could not open the database: {e}")),
            },
        }
    }

    pub fn path(&self) -> &PathBuf {
        &self.path
    }

    pub fn enabled(&self) -> bool {
        self.conn.is_some()
    }

    /// Why the cache is unavailable, for a caller that has to explain itself.
    pub fn unavailable_reason(&self) -> Option<String> {
        self.reason.clone()
    }

    /// The SQLite version compiled into this binary — a host fact the doctor reports.
    pub fn engine(&self) -> String {
        format!("bundled SQLite {}", rusqlite::version())
    }

    fn init(&self) {
        let _ = self.exec(
            "CREATE TABLE IF NOT EXISTS pages (
                 url TEXT PRIMARY KEY,
                 title TEXT NOT NULL DEFAULT '',
                 text TEXT NOT NULL DEFAULT '',
                 fetched_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
             )",
            params![],
        );
    }

    fn exec(&self, sql: &str, params: impl rusqlite::Params) -> Result<usize, String> {
        let Some(conn) = &self.conn else {
            return Err(self
                .unavailable_reason()
                .unwrap_or_else(|| "the local cache is unavailable".to_string()));
        };
        conn.execute(sql, params)
            .map_err(|e| format!("cache write failed: {e}"))
    }

    pub fn put(&self, page: &Page) -> Result<(), String> {
        // Values are BOUND, never interpolated: page text came off the web and is hostile input.
        self.exec(
            "INSERT INTO pages (url, title, text, fetched_at) VALUES (?1, ?2, ?3, CURRENT_TIMESTAMP)
             ON CONFLICT(url) DO UPDATE SET title=?2, text=?3, fetched_at=CURRENT_TIMESTAMP",
            params![page.url, page.title, page.text],
        )
        .map(|_| ())
    }

    pub fn get(&self, url: &str) -> Result<Option<Page>, String> {
        let Some(conn) = &self.conn else {
            return Err(self
                .unavailable_reason()
                .unwrap_or_else(|| "the local cache is unavailable".to_string()));
        };
        let mut stmt = conn
            .prepare("SELECT url, title, text FROM pages WHERE url = ?1")
            .map_err(|e| format!("cache read failed: {e}"))?;
        let mut rows = stmt
            .query_map(params![url], row_to_page)
            .map_err(|e| format!("cache read failed: {e}"))?;
        match rows.next() {
            Some(Ok(page)) => Ok(Some(page)),
            Some(Err(e)) => Err(format!("cache read failed: {e}")),
            None => Ok(None),
        }
    }

    /// Search the local corpus. Every term must appear (AND) — which is what "find what I already
    /// read" means in practice. LIKE is used rather than FTS5 because availability of the FTS
    /// tokenizers varies by build, and the corpus here is documentation pages.
    pub fn search(&self, query: &str, limit: usize) -> Result<Vec<Page>, String> {
        let Some(conn) = &self.conn else {
            return Err(self
                .unavailable_reason()
                .unwrap_or_else(|| "the local cache is unavailable".to_string()));
        };
        let terms: Vec<String> = query
            .split_whitespace()
            .map(|t| {
                // LIKE metacharacters are ESCAPED: a caller searching for "50%" or "a_b" must not
                // silently turn into a wildcard that matches the whole corpus.
                let escaped = t
                    .to_lowercase()
                    .replace('\\', "\\\\")
                    .replace('%', "\\%")
                    .replace('_', "\\_");
                format!("%{escaped}%")
            })
            .collect();
        if terms.is_empty() {
            return Ok(Vec::new());
        }
        let mut sql = String::from("SELECT url, title, text FROM pages WHERE ");
        for i in 0..terms.len() {
            if i > 0 {
                sql.push_str(" AND ");
            }
            sql.push_str(&format!(
                "(lower(title) LIKE ?{n} ESCAPE '\\' OR lower(text) LIKE ?{n} ESCAPE '\\')",
                n = i + 1
            ));
        }
        sql.push_str(" LIMIT ?");
        let limit_i64 = limit.min(500) as i64;
        let mut bound: Vec<&dyn rusqlite::ToSql> = terms
            .iter()
            .map(|t| t as &dyn rusqlite::ToSql)
            .collect();
        bound.push(&limit_i64);
        let mut stmt = conn
            .prepare(&sql)
            .map_err(|e| format!("cache search failed: {e}"))?;
        let rows = stmt
            .query_map(bound.as_slice(), row_to_page)
            .map_err(|e| format!("cache search failed: {e}"))?;
        let mut out = Vec::new();
        for row in rows {
            out.push(row.map_err(|e| format!("cache search failed: {e}"))?);
        }
        Ok(out)
    }

    pub fn count(&self) -> Result<usize, String> {
        let Some(conn) = &self.conn else {
            return Err(self
                .unavailable_reason()
                .unwrap_or_else(|| "the local cache is unavailable".to_string()));
        };
        conn.query_row("SELECT count(*) FROM pages", [], |r| r.get::<_, i64>(0))
            .map(|n| n as usize)
            .map_err(|e| format!("cache count failed: {e}"))
    }
}

fn row_to_page(row: &rusqlite::Row<'_>) -> rusqlite::Result<Page> {
    Ok(Page {
        url: row.get(0)?,
        title: row.get(1)?,
        text: row.get(2)?,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn temp_cache(tag: &str) -> Cache {
        let dir = std::env::temp_dir().join(format!(
            "fleet-search-{tag}-{}-{:?}",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .map(|d| d.as_nanos())
                .unwrap_or(0)
        ));
        Cache::open(dir.join("t.sqlite3"))
    }

    #[test]
    fn the_cache_is_available_with_no_external_binary() {
        // The whole point of bundling: no sqlite3 CLI, no Python, still a working database.
        let cache = temp_cache("engine");
        assert!(cache.enabled(), "{:?}", cache.unavailable_reason());
        assert!(cache.engine().contains("SQLite"), "{}", cache.engine());
    }

    #[test]
    fn round_trip_stores_and_finds_a_page() {
        let cache = temp_cache("roundtrip");
        let page = Page {
            url: "https://example.test/one".into(),
            title: "SearXNG configuration".into(),
            text: "the limiter can be disabled for a private instance".into(),
        };
        cache.put(&page).expect("put");
        assert_eq!(cache.get(&page.url).expect("get").as_ref(), Some(&page));

        let hits = cache.search("limiter private", 10).expect("search");
        assert_eq!(hits.len(), 1, "{hits:?}");
        assert_eq!(hits[0].url, page.url);
        assert!(
            cache.search("limiter absent", 10).expect("search").is_empty(),
            "every term must match"
        );
    }

    #[test]
    fn re_storing_a_url_refreshes_it_instead_of_duplicating_it() {
        let cache = temp_cache("refresh");
        let url = "https://example.test/doc";
        cache
            .put(&Page {
                url: url.into(),
                title: "v1".into(),
                text: "first".into(),
            })
            .expect("put");
        cache
            .put(&Page {
                url: url.into(),
                title: "v2".into(),
                text: "second".into(),
            })
            .expect("put");
        assert_eq!(cache.count().expect("count"), 1, "one URL is one row");
        assert_eq!(cache.get(url).expect("get").unwrap().title, "v2");
    }

    #[test]
    fn hostile_page_text_cannot_break_the_cache() {
        let cache = temp_cache("hostile");
        let hostile = Page {
            url: "https://example.test/quotes".into(),
            title: "Robustness".into(),
            text: "some of 'these' are \"quoted\"; DROP TABLE pages; -- and % is a LIKE wildcard".into(),
        };
        let plain = Page {
            url: "https://example.test/plain".into(),
            title: "Ordinary".into(),
            text: "nothing remarkable here".into(),
        };
        cache.put(&hostile).expect("put must survive quote-laden text");
        cache.put(&plain).expect("put");
        assert_eq!(cache.get(&hostile.url).expect("get").as_ref(), Some(&hostile));
        assert_eq!(cache.count().expect("count"), 2, "the table must still exist");

        // A '%' from the caller is matched LITERALLY: it finds the page that contains a '%', and
        // NOT the one that does not. If it were treated as a wildcard, both would come back — and
        // the escaping is what makes the difference.
        let hits = cache.search("%", 10).expect("search");
        assert_eq!(hits.len(), 1, "a bare % must not match the whole corpus: {hits:?}");
        assert_eq!(hits[0].url, hostile.url);
    }
}
