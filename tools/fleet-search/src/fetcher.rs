//! The one place that talks HTTP.
//!
//! Both `web_search` and `web_fetch` go through here, so timeouts, the user agent, and the size
//! cap are decided once. A search tool that an agent runs unattended must never hang on a dead
//! host, and must never let one enormous page decide how much memory it needs.

use std::io::Read;
use std::time::Duration;

pub const UA: &str = concat!(
    "fleet-search/",
    env!("CARGO_PKG_VERSION"),
    " (+https://github.com/lukemcqueen/hermes-cortex)"
);

/// 2 MiB of body. Documentation pages fit easily; anything larger is not something an agent is
/// going to read in a context window anyway.
pub const MAX_BYTES: u64 = 2 * 1024 * 1024;

pub fn get(url: &str) -> Result<(u16, String), String> {
    let agent = ureq::AgentBuilder::new()
        .timeout(Duration::from_secs(20))
        .user_agent(UA)
        .build();
    let response = agent
        .get(url)
        .call()
        .map_err(|e| format!("GET {url} failed: {e}"))?;
    let status = response.status();
    let mut bytes = Vec::new();
    response
        .into_reader()
        .take(MAX_BYTES)
        .read_to_end(&mut bytes)
        .map_err(|e| format!("GET {url}: could not read body: {e}"))?;
    // `errors=replace`: a page with one bad byte is still readable, and refusing it would report
    // a decoding problem as an unreachable page.
    Ok((status, String::from_utf8_lossy(&bytes).to_string()))
}

pub fn get_ok(url: &str) -> Result<String, String> {
    let (status, body) = get(url)?;
    if !(200..300).contains(&status) {
        return Err(format!("GET {url}: HTTP {status}"));
    }
    Ok(body)
}

/// Percent-encode for a query string. Unreserved characters pass through; everything else is
/// encoded by UTF-8 byte, which is what a search endpoint expects.
pub fn urlencode(s: &str) -> String {
    let mut out = String::with_capacity(s.len());
    for byte in s.as_bytes() {
        match byte {
            b'A'..=b'Z' | b'a'..=b'z' | b'0'..=b'9' | b'-' | b'_' | b'.' | b'~' => out.push(*byte as char),
            _ => out.push_str(&format!("%{byte:02X}")),
        }
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn urlencode_handles_the_characters_queries_actually_contain() {
        assert_eq!(urlencode("rust search"), "rust%20search");
        assert_eq!(urlencode("a&b=c?d"), "a%26b%3Dc%3Fd");
        assert_eq!(urlencode("sécurité"), "s%C3%A9curit%C3%A9");
    }
}
