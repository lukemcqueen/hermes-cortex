//! HTML → text, with no dependency.
//!
//! `web_fetch` exists so an agent can read a page, and an agent reads TEXT. Pulling in a full
//! HTML parser to do that would add tens of crates and a C parser boundary to a tool whose whole
//! pitch is "small and boring". The rules below are the ones that actually matter for reading:
//! never let a <script> or <style> body reach the output, drop the tags, decode the entities that
//! appear in real prose, and collapse the whitespace that markup leaves behind.

/// Tags whose CONTENT must never appear in the text.
const OPAQUE: [&str; 4] = ["script", "style", "noscript", "svg"];

/// Strip HTML to readable text.
pub fn to_text(html: &str) -> String {
    let mut out = String::with_capacity(html.len() / 2);
    let mut rest = html;

    while let Some(open) = rest.find('<') {
        out.push_str(&rest[..open]);
        // A tag is a COMMENT, a DOCTYPE, or a name.
        if rest[open..].starts_with("<!--") {
            match rest[open..].find("-->") {
                Some(end) => rest = &rest[open + end + 3..],
                None => return finish(&out),
            }
            continue;
        }
        let Some(close) = rest[open..].find('>') else {
            // No closing `>`: keep the remainder as LITERAL text rather than dropping it. We
            // cannot parse it, and silently truncating a page is worse than a stray `<`.
            // (Pushing `rest` wholesale here would duplicate the text already emitted above.)
            out.push_str(&rest[open..]);
            rest = "";
            break;
        };
        let tag_body = &rest[open + 1..open + close];
        rest = &rest[open + close + 1..];

        let name = tag_name(tag_body);
        // Block-ish tags become a newline so paragraphs do not run together.
        if matches!(
            name.as_str(),
            "p" | "br" | "div" | "li" | "tr" | "h1" | "h2" | "h3" | "h4" | "h5" | "h6" | "section" | "article"
        ) {
            out.push('\n');
        }
        if OPAQUE.contains(&name.as_str()) && !tag_body.starts_with('/') {
            // Skip to the matching close tag. Nested same-name tags are vanishingly rare inside
            // these four, and the cost of being wrong is only a shorter text, never executed markup.
            let closer = format!("</{name}");
            match rest.to_ascii_lowercase().find(&closer) {
                Some(end) => {
                    rest = &rest[end..];
                    if let Some(gt) = rest.find('>') {
                        rest = &rest[gt + 1..];
                    }
                }
                None => break,
            }
        }
    }
    out.push_str(rest);
    finish(&out)
}

fn tag_name(tag_body: &str) -> String {
    let body = tag_body.trim_start_matches('/');
    let name: String = body
        .chars()
        .take_while(|c| c.is_ascii_alphanumeric())
        .collect();
    name.to_ascii_lowercase()
}

fn finish(raw: &str) -> String {
    let decoded = decode_entities(raw);
    // Collapse runs of blank space; keep paragraph breaks as a single newline.
    let mut out = String::with_capacity(decoded.len());
    let mut blank_run = 0usize;
    for line in decoded.lines() {
        let trimmed = line.split_whitespace().collect::<Vec<_>>().join(" ");
        if trimmed.is_empty() {
            blank_run += 1;
            continue;
        }
        if !out.is_empty() {
            out.push('\n');
            if blank_run > 0 {
                out.push('\n');
            }
        }
        blank_run = 0;
        out.push_str(&trimmed);
    }
    out.trim().to_string()
}

/// The entities that occur in real prose. Numeric forms are handled generically.
pub fn decode_entities(s: &str) -> String {
    let mut out = String::with_capacity(s.len());
    let mut rest = s;
    while let Some(amp) = rest.find('&') {
        out.push_str(&rest[..amp]);
        let tail = &rest[amp..];
        let Some(semi) = tail[..tail.len().min(12)].find(';').map(|i| i) else {
            out.push('&');
            rest = &tail[1..];
            continue;
        };
        let entity = &tail[1..semi];
        let replacement = match entity {
            "amp" => Some('&'),
            "lt" => Some('<'),
            "gt" => Some('>'),
            "quot" => Some('"'),
            "apos" | "#39" => Some('\''),
            "nbsp" => Some(' '),
            "mdash" => Some('—'),
            "ndash" => Some('–'),
            "hellip" => Some('…'),
            _ => entity
                .strip_prefix("#x")
                .or_else(|| entity.strip_prefix("#X"))
                .and_then(|hex| u32::from_str_radix(hex, 16).ok())
                .or_else(|| {
                    entity
                        .strip_prefix('#')
                        .and_then(|dec| dec.parse::<u32>().ok())
                })
                .and_then(char::from_u32),
        };
        match replacement {
            Some(c) => {
                out.push(c);
                rest = &tail[semi + 1..];
            }
            None => {
                out.push('&');
                rest = &tail[1..];
            }
        }
    }
    out.push_str(rest);
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn script_and_style_bodies_never_reach_the_text() {
        let html = "<p>before</p><script>var secret = 'LEAK';</script><style>.x{color:red}</style><p>after</p>";
        let text = to_text(html);
        assert!(text.contains("before") && text.contains("after"), "{text}");
        assert!(!text.contains("LEAK"), "script body leaked: {text}");
        assert!(!text.contains("color:red"), "style body leaked: {text}");
    }

    #[test]
    fn entities_and_whitespace_are_normalised() {
        let text = to_text("<div>a &amp; b&nbsp;&mdash; c &#65; &#x42;</div>");
        assert!(text.contains("a & b — c A B"), "{text}");
        assert!(!text.contains("  "), "runs of spaces should collapse: {text}");
    }

    #[test]
    fn an_unterminated_tag_does_not_panic_and_does_not_duplicate_text() {
        // A stray `<` is unparseable, so the honest thing is to keep it verbatim — and to keep it
        // ONCE. The first version of this function emitted the preceding text twice here.
        let text = to_text("<p>text<div");
        assert_eq!(text, "text<div", "{text}");
        assert_eq!(text.matches("text").count(), 1, "the preceding text must appear ONCE: {text}");
        assert!(to_text("no tags at all").contains("no tags at all"));
    }

    #[test]
    fn comments_are_dropped() {
        let text = to_text("a<!-- hidden -->b");
        assert_eq!(text, "ab");
    }
}
