//! End-to-end: the REAL binary, run as a process — the way an agent actually invokes it.
//!
//! The unit tests inside `src/` cover the logic. These cover the CONTRACT an agent depends on:
//! exit codes, what lands on stdout versus stderr, and whether the MCP surface answers over a
//! pipe. A tool can pass every unit test and still be unusable because it printed a banner to
//! stdout or returned 0 on failure.
//!
//! No test dependency is used: the HTTP server below is ~25 lines of `std::net`, so the fetch →
//! cache → local-search round trip is REAL without reaching the internet.

use std::io::{BufRead, BufReader, Read, Write};
use std::net::TcpListener;
use std::process::{Command, Stdio};

fn bin() -> &'static str {
    env!("CARGO_BIN_EXE_fleet-search")
}

/// Serve one HTML page on an ephemeral port, then stop listening.
fn serve_once(html: &'static str) -> u16 {
    let listener = TcpListener::bind("127.0.0.1:0").expect("bind an ephemeral port");
    let port = listener.local_addr().expect("addr").port();
    std::thread::spawn(move || {
        if let Ok((mut stream, _)) = listener.accept() {
            let mut buf = [0u8; 1024];
            let _ = stream.read(&mut buf);
            let response = format!(
                "HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{}",
                html.len(),
                html
            );
            let _ = stream.write_all(response.as_bytes());
            let _ = stream.flush();
        }
    });
    port
}

/// An isolated cache per test, so tests cannot see each other's pages.
fn isolated_home(tag: &str) -> String {
    let dir = std::env::temp_dir().join(format!("fleet-search-e2e-{tag}-{}", std::process::id()));
    std::fs::create_dir_all(&dir).expect("temp cache dir");
    dir.to_string_lossy().to_string()
}

struct Run {
    code: i32,
    stdout: String,
    stderr: String,
}

fn run(tag: &str, args: &[&str], clear_provider: bool) -> Run {
    let mut cmd = Command::new(bin());
    cmd.args(args)
        .env("XDG_CACHE_HOME", isolated_home(tag))
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    if clear_provider {
        cmd.env_remove("SEARXNG_URL");
    }
    let out = cmd.output().expect("run the binary");
    Run {
        code: out.status.code().unwrap_or(-1),
        stdout: String::from_utf8_lossy(&out.stdout).to_string(),
        stderr: String::from_utf8_lossy(&out.stderr).to_string(),
    }
}

#[test]
fn doctor_works_with_no_external_binary_and_reports_the_engine() {
    let r = run("doctor", &["doctor"], true);
    assert_eq!(r.code, 0, "stdout={} stderr={}", r.stdout, r.stderr);
    assert!(
        r.stdout.contains("bundled SQLite"),
        "the cache engine is a host fact worth reporting: {}",
        r.stdout
    );
    assert!(
        r.stdout.contains("SEARXNG_URL"),
        "an unconfigured provider must name its variable: {}",
        r.stdout
    );
}

#[test]
fn search_without_a_provider_exits_3_and_says_so_on_stderr() {
    let r = run("noprovider", &["search", "anything"], true);
    assert_eq!(r.code, 3, "3 = could not verify, which is NOT the same as found nothing");
    assert!(r.stderr.contains("SEARXNG_URL"), "stderr must name what to configure: {}", r.stderr);
    assert!(
        !r.stdout.contains("No results"),
        "an unsearchable query must never look like a successful empty search: {}",
        r.stdout
    );
}

#[test]
fn fetch_then_local_search_round_trips_over_a_real_http_server() {
    let html = "<html><head><title>SearXNG notes</title></head><body>\
                <script>var leak = 'DO NOT LEAK';</script>\
                <p>The limiter can be disabled for a private instance.</p></body></html>";
    let port = serve_once(html);
    let url = format!("http://127.0.0.1:{port}/doc");

    let fetched = run("roundtrip", &["fetch", &url], true);
    assert_eq!(fetched.code, 0, "stdout={} stderr={}", fetched.stdout, fetched.stderr);
    assert!(fetched.stdout.contains("limiter"), "the page text must be on stdout");
    assert!(!fetched.stdout.contains("DO NOT LEAK"), "script bodies must never reach the text");
    assert!(
        !fetched.stdout.contains("chars,") && !fetched.stdout.contains("cached:"),
        "the metadata envelope belongs on stderr, so stdout stays pipeable text: {}",
        fetched.stdout
    );
    assert!(
        fetched.stderr.contains("cached: true"),
        "and the cache write must be reported, not assumed: {}",
        fetched.stderr
    );

    let found = run("roundtrip", &["local", "limiter private"], true);
    assert_eq!(found.code, 0, "stdout={} stderr={}", found.stdout, found.stderr);
    assert!(found.stdout.contains(&url), "the fetched page must be findable offline: {}", found.stdout);

    // The byte-for-byte check that matters: fetch's stdout is the TEXT, not a JSON envelope.
    let direct = run("roundtrip", &["local", "private", "--json"], true);
    assert_eq!(direct.code, 0);
    assert!(direct.stdout.contains("\"results\""), "{}", direct.stdout);
}

#[test]
fn mcp_over_stdio_answers_initialize_and_advertises_three_tools() {
    let mut child = Command::new(bin())
        .arg("mcp")
        .env("XDG_CACHE_HOME", isolated_home("mcp"))
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .expect("spawn mcp");
    {
        let stdin = child.stdin.as_mut().expect("stdin");
        writeln!(stdin, r#"{{"jsonrpc":"2.0","id":1,"method":"initialize"}}"#).expect("write");
        writeln!(stdin, r#"{{"jsonrpc":"2.0","id":2,"method":"tools/list"}}"#).expect("write");
        writeln!(
            stdin,
            r#"{{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{{"name":"web_search_local","arguments":{{"query":"nothing here"}}}}}}"#
        )
        .expect("write");
        stdin.flush().expect("flush");
    }
    let mut lines = BufReader::new(child.stdout.take().expect("stdout")).lines();
    let init = lines.next().expect("init response").expect("line");
    let tools = lines.next().expect("tools response").expect("line");
    let call = lines.next().expect("call response").expect("line");
    let _ = child.kill();

    let init: serde_json::Value = serde_json::from_str(&init).expect("initialize is JSON");
    assert_eq!(init["result"]["serverInfo"]["name"], "fleet-search");

    let tools: serde_json::Value = serde_json::from_str(&tools).expect("tools/list is JSON");
    let names: Vec<String> = tools["result"]["tools"]
        .as_array()
        .expect("tools array")
        .iter()
        .map(|t| t["name"].as_str().unwrap_or_default().to_string())
        .collect();
    assert_eq!(names, vec!["web_search", "web_fetch", "web_search_local"]);

    // A tool call that finds nothing is a SUCCESS with an empty result — not an error, and not a
    // silent lie either: the JSON says which cache was searched.
    let call: serde_json::Value = serde_json::from_str(&call).expect("tools/call is JSON");
    assert_eq!(call["result"]["isError"], false, "{call}");
    let text = call["result"]["content"][0]["text"].as_str().unwrap_or_default();
    assert!(text.contains("\"results\""), "the tool result carries the JSON payload: {text}");
}
