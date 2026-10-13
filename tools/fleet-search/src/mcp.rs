//! `fleet-search mcp` — the same three operations, over MCP on stdio.
//!
//! The point of this surface is that it needs no daemon and no port: an MCP client starts the
//! process, speaks JSON-RPC over its stdin/stdout, and the process exits with it. That is how one
//! binary serves a Python agent system (hermes-cortex registers it in `mcp_servers`) and a Rust
//! one (steadfaste can run it as a worker tool) without either of them owning a search service.
//!
//! TWO DISCIPLINES THIS FILE MUST KEEP:
//!   1. stdout carries JSON-RPC and NOTHING else. One stray `println!` corrupts the stream and the
//!      client reports a protocol error that has nothing to do with the actual bug. Diagnostics go
//!      to stderr, always.
//!   2. A tool that failed is reported as an ERROR RESULT (`isError: true`), never as a successful
//!      call returning an empty list. An agent must be able to tell "found nothing" from "could not
//!      look", because only one of those is worth retrying.

use std::io::{BufRead, Write};

use serde_json::{json, Value};

use crate::cache::Cache;
use crate::ops;

pub fn serve(cache: &Cache) -> std::io::Result<()> {
    let stdin = std::io::stdin();
    let mut stdout = std::io::stdout();
    for line in stdin.lock().lines() {
        let line = line?;
        if line.trim().is_empty() {
            continue;
        }
        let request: Value = match serde_json::from_str(&line) {
            Ok(v) => v,
            Err(e) => {
                // A parse failure has no id to answer to, so it can only be logged.
                eprintln!("fleet-search mcp: ignoring unparseable line: {e}");
                continue;
            }
        };
        let id = request.get("id").cloned();
        let method = request.get("method").and_then(|m| m.as_str()).unwrap_or("").to_string();

        // Notifications carry no id and get no response — answering one is a protocol error.
        if id.is_none() {
            continue;
        }

        let result = handle(&method, request.get("params"), cache);
        let payload = match result {
            Ok(value) => json!({"jsonrpc": "2.0", "id": id, "result": value}),
            Err((code, message)) => {
                json!({"jsonrpc": "2.0", "id": id, "error": {"code": code, "message": message}})
            }
        };
        writeln!(stdout, "{payload}")?;
        stdout.flush()?;
    }
    Ok(())
}

fn handle(method: &str, params: Option<&Value>, cache: &Cache) -> Result<Value, (i64, String)> {
    match method {
        "initialize" => Ok(json!({
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "fleet-search", "version": env!("CARGO_PKG_VERSION")},
        })),
        "ping" => Ok(json!({})),
        "tools/list" => Ok(json!({
            "tools": ops::OPERATIONS.iter().map(|op| json!({
                "name": op.name,
                "description": op.summary,
                "inputSchema": schema_for(op.name),
            })).collect::<Vec<_>>()
        })),
        "tools/call" => {
            let params = params.ok_or((-32602, "tools/call requires params".to_string()))?;
            let name = params
                .get("name")
                .and_then(|n| n.as_str())
                .ok_or((-32602, "tools/call requires a tool name".to_string()))?;
            let args = params.get("arguments").cloned().unwrap_or_else(|| json!({}));
            let text = call(name, &args, cache).map_err(|e| (-32000, e))?;
            Ok(json!({
                "content": [{"type": "text", "text": text}],
                "isError": false,
            }))
        }
        other => Err((-32601, format!("method not found: {other}"))),
    }
}

/// Dispatch a tool call. A failure comes back as a RESULT carrying `isError`, which is what the
/// caller needs to distinguish "nothing found" from "could not look".
fn call(name: &str, args: &Value, cache: &Cache) -> Result<String, String> {
    let query = || {
        args.get("query")
            .and_then(|q| q.as_str())
            .map(|s| s.to_string())
            .ok_or_else(|| format!("{name} requires a `query` argument"))
    };
    let limit = || {
        args.get("limit")
            .and_then(|l| l.as_u64())
            .map(|l| l as usize)
            .unwrap_or(10)
    };

    let outcome = match name {
        "web_search" => ops::web_search(&query()?, limit()).and_then(to_json),
        "web_fetch" => {
            let url = args
                .get("url")
                .and_then(|u| u.as_str())
                .ok_or("web_fetch requires a `url` argument")?;
            ops::web_fetch(url, cache).and_then(to_json)
        }
        "web_search_local" => ops::web_search_local(&query()?, limit(), cache).and_then(to_json),
        other => Err(format!("unknown tool: {other}")),
    };

    match outcome {
        Ok(text) => Ok(text),
        // The MCP-level failure: mark it as an error so the agent does not read it as "no results".
        Err(e) => Err(format!("{name}: {e}")),
    }
}

fn to_json<T: serde::Serialize>(value: T) -> Result<String, String> {
    serde_json::to_string_pretty(&value).map_err(|e| format!("could not serialise the result: {e}"))
}

/// The input schema for an operation. Derived from the same table the CLI advertises, so the two
/// surfaces cannot describe one operation differently.
fn schema_for(name: &str) -> Value {
    match name {
        "web_fetch" => json!({
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Absolute http(s) URL to fetch."}
            },
            "required": ["url"]
        }),
        _ => json!({
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "What to look for."},
                "limit": {"type": "integer", "minimum": 1, "maximum": 500, "default": 10}
            },
            "required": ["query"]
        }),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::provider;

    fn cache() -> Cache {
        let dir = std::env::temp_dir().join(format!("fleet-search-mcp-{}", std::process::id()));
        Cache::open(dir.join("mcp.sqlite3"))
    }

    #[test]
    fn initialize_announces_the_tools_capability() {
        let out = handle("initialize", None, &cache()).expect("initialize");
        assert_eq!(out["capabilities"]["tools"], json!({}));
        assert_eq!(out["serverInfo"]["name"], "fleet-search");
    }

    #[test]
    fn tools_list_is_generated_from_the_operations_table() {
        let out = handle("tools/list", None, &cache()).expect("tools/list");
        let tools = out["tools"].as_array().expect("array");
        assert_eq!(tools.len(), ops::OPERATIONS.len());
        for op in ops::OPERATIONS.iter() {
            let tool = tools.iter().find(|t| t["name"] == op.name).expect("advertised");
            assert_eq!(tool["description"], op.summary);
            assert_eq!(tool["inputSchema"]["type"], "object");
        }
    }

    #[test]
    fn a_failing_tool_is_an_error_not_an_empty_result() {
        // No provider configured in the test environment, so web_search must FAIL — and the
        // failure must be legible, not a silent empty list.
        std::env::remove_var(provider::SEARXNG_ENV);
        let err = call("web_search", &json!({"query": "anything"}), &cache()).unwrap_err();
        assert!(err.contains("web_search"), "{err}");
        assert!(err.contains(provider::SEARXNG_ENV), "the error must name what to configure: {err}");
    }

    #[test]
    fn an_unknown_method_is_a_protocol_error_not_a_crash() {
        let err = handle("tools/nonsense", None, &cache()).unwrap_err();
        assert_eq!(err.0, -32601);
    }
}
