//! Search providers — and the honest behaviour when there is none.
//!
//! SearXNG is an OPTIONAL external provider, never a permanent dependency:
//!
//! * Set `SEARXNG_URL` (e.g. `http://127.0.0.1:8888`) and `web_search` uses it.
//! * Leave it unset and `web_search` says NO PROVIDER IS CONFIGURED and exits 3.
//!
//! That third behaviour is the important one. Scraping free public search pages is fragile and
//! rate-limited, and a tool that silently returns an empty list when it could not search is
//! indistinguishable from a tool that searched and found nothing. `web_search_local` needs no
//! provider at all — it reads what we already fetched — so the durable half of this capability
//! keeps working on a host with no network.

use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct Hit {
    pub title: String,
    pub url: String,
    pub snippet: String,
}

/// What a provider returned: the hits, and which engines could not answer.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct Outcome {
    pub hits: Vec<Hit>,
    /// Engine names that were unreachable or refused. SearXNG reports this and it is NOT noise:
    /// with zero hits it is the difference between "nothing matched" (the query is the problem)
    /// and "the engines that could answer were blocked" (the host is) — and only one of those is
    /// worth retrying. Measured 2026-10-13: `brave` and `duckduckgo` are unresponsive from a
    /// datacenter IP, which is exactly how a search returns zero results while looking healthy.
    pub unresponsive: Vec<String>,
}

pub const SEARXNG_ENV: &str = "SEARXNG_URL";

#[derive(Debug, PartialEq)]
pub enum ProviderError {
    /// No provider configured — not a failure of the query.
    NotConfigured,
    /// The provider could not be reached.
    Http(String),
    /// The provider answered in a shape we do not understand.
    Shape(String),
}

impl ProviderError {
    pub fn message(&self) -> String {
        match self {
            ProviderError::NotConfigured => format!(
                "no search provider is configured: set {SEARXNG_ENV} to a SearXNG base URL \
                 (e.g. http://127.0.0.1:8888). `web_search_local` works without one."
            ),
            ProviderError::Http(e) => format!("search provider unreachable: {e}"),
            ProviderError::Shape(e) => format!("search provider answered unexpectedly: {e}"),
        }
    }
}

/// The configured provider's base URL, if any.
pub fn configured() -> Option<String> {
    std::env::var(SEARXNG_ENV)
        .ok()
        .map(|u| u.trim().to_string())
        .filter(|u| !u.is_empty())
}

/// Parse a SearXNG JSON body. Pure, so the contract is testable without a server: this is the
/// function to update when the upstream shape changes, and the tests here say exactly what we
/// depend on.
pub fn parse_searxng(body: &str, limit: usize) -> Result<Outcome, ProviderError> {
    let value: serde_json::Value = serde_json::from_str(body)
        .map_err(|e| ProviderError::Shape(format!("body is not JSON: {e}")))?;
    let results = value
        .get("results")
        .and_then(|r| r.as_array())
        .ok_or_else(|| ProviderError::Shape("no `results` array in the response".to_string()))?;
    let hits: Vec<Hit> = results
        .iter()
        .take(limit)
        .filter_map(|r| {
            // A result with no URL cannot be followed, so it is not a result.
            let url = r.get("url")?.as_str()?.trim().to_string();
            if url.is_empty() {
                return None;
            }
            Some(Hit {
                title: r.get("title").and_then(|t| t.as_str()).unwrap_or("").trim().to_string(),
                url,
                snippet: r.get("content").and_then(|c| c.as_str()).unwrap_or("").trim().to_string(),
            })
        })
        .collect();

    // `unresponsive_engines` is a list of [engine, reason] pairs (or bare names, by version).
    let unresponsive = value
        .get("unresponsive_engines")
        .and_then(|u| u.as_array())
        .map(|engines| {
            engines
                .iter()
                .filter_map(|e| match e {
                    serde_json::Value::Array(pair) => pair.first(),
                    other => Some(other),
                })
                .filter_map(|n| n.as_str())
                .map(|n| n.trim().to_string())
                .filter(|n| !n.is_empty())
                .collect()
        })
        .unwrap_or_default();

    Ok(Outcome { hits, unresponsive })
}

pub fn search(query: &str, limit: usize) -> Result<Outcome, ProviderError> {
    let Some(base) = configured() else {
        return Err(ProviderError::NotConfigured);
    };
    let url = format!(
        "{}/search?q={}&format=json",
        base.trim_end_matches('/'),
        crate::fetcher::urlencode(query)
    );
    let body = crate::fetcher::get_ok(&url).map_err(ProviderError::Http)?;
    parse_searxng(&body, limit)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_a_searxng_response_and_skips_unfollowable_results() {
        let body = r#"{"query":"x","results":[
            {"title":"One","url":"https://a.test/1","content":"first"},
            {"title":"No URL"},
            {"title":"Empty URL","url":"   "},
            {"title":"Two","url":"https://b.test/2","content":"second"}
        ]}"#;
        let out = parse_searxng(body, 10).expect("parse");
        let hits = out.hits;
        assert_eq!(hits.len(), 2, "results without a usable URL are not results: {hits:?}");
        assert_eq!(hits[0].title, "One");
        assert_eq!(hits[1].url, "https://b.test/2");
    }

    #[test]
    fn unresponsive_engines_are_surfaced_in_both_shapes() {
        // SearXNG reports [engine, reason] pairs, and bare names in some versions.
        let body = r#"{"results":[],"unresponsive_engines":[["brave","timeout"],["duckduckgo","403"],"wikidata"]}"#;
        let out = parse_searxng(body, 10).expect("parse");
        assert!(out.hits.is_empty());
        assert_eq!(
            out.unresponsive,
            vec!["brave", "duckduckgo", "wikidata"],
            "an unresponsive engine must survive parsing — it is what separates a blocked host \
             from a query that found nothing"
        );

        // A body without the field is simply empty there, never an error.
        let clean = parse_searxng(r#"{"results":[{"url":"https://a.test/1"}]}"#, 10).expect("parse");
        assert!(clean.unresponsive.is_empty());
        assert_eq!(clean.hits.len(), 1);
    }

    #[test]
    fn respects_the_limit() {
        let body = r#"{"results":[{"url":"1"},{"url":"2"},{"url":"3"}]}"#;
        assert_eq!(parse_searxng(body, 2).expect("parse").hits.len(), 2);
    }

    #[test]
    fn a_wrong_shape_is_reported_as_a_shape_problem_not_an_empty_result() {
        // An HTML error page from a misconfigured instance is the realistic case here.
        let err = parse_searxng("<html>not json</html>", 10).unwrap_err();
        assert!(matches!(err, ProviderError::Shape(_)), "{err:?}");
        // A JSON body with no `results` key is also a shape problem, not "found nothing".
        let err = parse_searxng(r#"{"error":"limiter"}"#, 10).unwrap_err();
        assert!(matches!(err, ProviderError::Shape(_)), "{err:?}");
    }

    #[test]
    fn no_provider_is_its_own_error() {
        let msg = ProviderError::NotConfigured.message();
        assert!(msg.contains(SEARXNG_ENV), "{msg}");
        assert!(msg.contains("web_search_local"), "the message must point at what still works: {msg}");
    }
}
