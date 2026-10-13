//! The three operations — defined ONCE, so the CLI and the MCP surface cannot drift.
//!
//! This module is the whole capability: `web_search`, `web_fetch`, `web_search_local`. Both front
//! doors call these functions, and the tool LIST the MCP surface advertises is generated from the
//! same table the CLI help is built from. A second implementation of "how search works" is how
//! two agent systems end up with two behaviours and one set of bugs.

use serde::Serialize;

use crate::cache::{Cache, Page};
use crate::htmltext;
use crate::provider::{self, Hit};

#[derive(Debug, Serialize)]
pub struct SearchOutput {
    pub query: String,
    pub provider: String,
    pub results: Vec<Hit>,
    /// Engines that could not answer. With zero results this is the ONLY thing separating
    /// "nothing matched" from "the engines that could answer were blocked" — see provider::Outcome.
    pub unresponsive: Vec<String>,
}

#[derive(Debug, Serialize)]
pub struct FetchOutput {
    pub url: String,
    pub title: String,
    pub chars: usize,
    pub cached: bool,
    /// True when the page was ALREADY stored — i.e. this call refreshed a known page.
    pub previously_cached: bool,
    pub text: String,
}

#[derive(Debug, Serialize)]
pub struct LocalOutput {
    pub query: String,
    pub cache: String,
    pub results: Vec<LocalHit>,
}

#[derive(Debug, Serialize)]
pub struct LocalHit {
    pub url: String,
    pub title: String,
    pub excerpt: String,
}

/// One advertised operation. The description lives HERE, so the MCP tool list and the CLI help
/// cannot describe the same operation differently.
pub struct Operation {
    pub name: &'static str,
    pub summary: &'static str,
    pub args: &'static [&'static str],
}

pub const OPERATIONS: [Operation; 3] = [
    Operation {
        name: "web_search",
        summary: "Search the web for a query. Requires a configured provider (SEARXNG_URL).",
        args: &["query", "limit"],
    },
    Operation {
        name: "web_fetch",
        summary: "Fetch a URL, convert it to text, and store it in the local cache.",
        args: &["url"],
    },
    Operation {
        name: "web_search_local",
        summary: "Search pages already fetched. Works offline and needs no provider.",
        args: &["query", "limit"],
    },
];

/// Hints an agent can act on, rather than prose it has to interpret.
pub fn hints(provider_configured: bool) -> Vec<String> {
    let mut out = Vec::new();
    if !provider_configured {
        out.push(format!(
            "web_search is unavailable until {} is set; web_search_local works now",
            provider::SEARXNG_ENV
        ));
    }
    out.push("web_fetch stores what it reads, so web_search_local can find it later".to_string());
    out
}

pub fn web_search(query: &str, limit: usize) -> Result<SearchOutput, String> {
    let outcome = provider::search(query, limit).map_err(|e| e.message())?;
    Ok(SearchOutput {
        query: query.to_string(),
        provider: provider::configured().unwrap_or_else(|| "none".to_string()),
        results: outcome.hits,
        unresponsive: outcome.unresponsive,
    })
}

/// Fetch a page, reduce it to text, and remember it.
///
/// The cache write is attempted on EVERY fetch: `web_search_local` is only as useful as the corpus
/// it can see, and a page read once should not need the network twice. A cache that could not be
/// written is reported, never hidden — the caller asked for a store, and silently not storing is
/// how "it worked" becomes a lie.
pub fn web_fetch(url: &str, cache: &Cache) -> Result<FetchOutput, String> {
    // Was this page already stored? Reporting a REFRESH as a first fetch would overstate what the
    // call did, and the cache is the thing agents will reason about later.
    let already = cache.get(url).ok().flatten().is_some();
    let html = crate::fetcher::get_ok(url)?;
    let text = htmltext::to_text(&html);
    let title = extract_title(&html).unwrap_or_else(|| url.to_string());
    let page = Page {
        url: url.to_string(),
        title: title.clone(),
        text: text.clone(),
    };
    let mut cache_note = false;
    let mut warning = None;
    if cache.enabled() {
        match cache.put(&page) {
            Ok(()) => cache_note = true,
            Err(e) => warning = Some(format!("could NOT cache this page: {e}")),
        }
    } else {
        warning = Some("local cache DISABLED (sqlite3 not on PATH) — this page was not stored".to_string());
    }
    if let Some(w) = warning {
        eprintln!("fleet-search: {w}");
    }
    Ok(FetchOutput {
        url: url.to_string(),
        title,
        chars: text.chars().count(),
        cached: cache_note,
        previously_cached: already,
        text,
    })
}

pub fn web_search_local(query: &str, limit: usize, cache: &Cache) -> Result<LocalOutput, String> {
    if !cache.enabled() {
        let why = cache
            .unavailable_reason()
            .unwrap_or_else(|| "no reason reported".to_string());
        return Err(format!(
            "the local cache is unavailable at {}, so there is nothing to search: {why}",
            cache.path().display()
        ));
    }
    let rows = cache.search(query, limit)?;
    Ok(LocalOutput {
        query: query.to_string(),
        cache: cache.path().display().to_string(),
        results: rows
            .into_iter()
            .map(|p| LocalHit {
                url: p.url,
                title: p.title,
                excerpt: excerpt(&p.text, query, 240),
            })
            .collect(),
    })
}

fn excerpt(text: &str, query: &str, width: usize) -> String {
    let first_term = query.split_whitespace().next().unwrap_or("");
    let lower = text.to_lowercase();
    let at = if first_term.is_empty() {
        0
    } else {
        lower.find(&first_term.to_lowercase()).unwrap_or(0)
    };
    let start = at.saturating_sub(width / 3);
    let slice: String = text.chars().skip(start).take(width).collect();
    slice.split_whitespace().collect::<Vec<_>>().join(" ")
}

/// The page's <title>, if it has one. Kept here rather than in htmltext because it is about
/// labelling a search result, not about rendering a page.
pub fn extract_title(html: &str) -> Option<String> {
    let lower = html.to_lowercase();
    let open = lower.find("<title")?;
    let after = html[open..].find('>')? + open + 1;
    let close = lower[after..].find("</title")? + after;
    let title = htmltext::decode_entities(&html[after..close]);
    let title = title.split_whitespace().collect::<Vec<_>>().join(" ");
    if title.is_empty() {
        None
    } else {
        Some(title)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn extracts_a_title_and_normalises_its_whitespace() {
        let html = "<html><head><TITLE> A  Page\n&mdash; Site </TITLE></head><body>x</body></html>";
        assert_eq!(extract_title(html).as_deref(), Some("A Page — Site"));
    }

    #[test]
    fn a_page_with_no_title_gets_none_rather_than_an_empty_string() {
        assert_eq!(extract_title("<html><body>no title</body></html>"), None);
        assert_eq!(extract_title("<title></title>"), None);
    }

    #[test]
    fn every_operation_is_advertised_once_with_the_args_it_takes() {
        let names: Vec<&str> = OPERATIONS.iter().map(|o| o.name).collect();
        assert_eq!(names, vec!["web_search", "web_fetch", "web_search_local"]);
        for op in OPERATIONS.iter() {
            assert!(!op.summary.is_empty(), "{} needs a summary", op.name);
            assert!(!op.args.is_empty(), "{} needs its args declared", op.name);
        }
    }

    #[test]
    fn hints_name_the_variable_that_unlocks_web_search() {
        let missing = hints(false);
        assert!(missing.iter().any(|h| h.contains(provider::SEARXNG_ENV)), "{missing:?}");
        assert!(missing.iter().any(|h| h.contains("web_search_local")), "{missing:?}");
        // On a host WITH a provider there is nothing to unlock, so no hint may say so.
        let configured = hints(true);
        assert!(
            !configured.iter().any(|h| h.contains("unavailable")),
            "a configured host must not be told web_search is unavailable: {configured:?}"
        );
    }
}
