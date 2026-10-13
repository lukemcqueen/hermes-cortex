//! fleet-search — one search capability for every fleet agent.
//!
//! See `docs/design/agent-search.md` for why this is a single static binary rather than a service,
//! and for the measured resource envelope behind that decision.
//!
//! EXIT CODES (documented because agents branch on them):
//!   0  the operation ran and its result is on stdout
//!   1  the operation ran and FAILED (unreachable provider, HTTP error, unusable response)
//!   3  COULD NOT VERIFY — nothing was searched, and no result should be inferred from it.
//!      `web_search` with no provider, `web_search_local` with no cache.
//!
//! 1 and 3 are deliberately different: one means "ask again later", the other means "this host is
//! not set up for it". Collapsing them is how an agent concludes a host is broken when it merely
//! lacks a variable.

mod cache;
mod fetcher;
mod htmltext;
mod mcp;
mod ops;
mod provider;

use clap::{Parser, Subcommand};
use std::process::ExitCode;

use cache::Cache;

const EXIT_OK: u8 = 0;
const EXIT_FAILED: u8 = 1;
const EXIT_COULD_NOT_VERIFY: u8 = 3;

#[derive(Parser)]
#[command(
    name = "fleet-search",
    version,
    about = "One search capability for every fleet agent (web search, fetch, local search)",
    after_help = "Provider: set SEARXNG_URL to enable web_search. web_fetch and web_search_local\n\
                  work without one — fetching stores what it reads in a local SQLite cache."
)]
struct Cli {
    #[command(subcommand)]
    command: Command,

    /// Emit JSON instead of human-readable text.
    #[arg(long, global = true)]
    json: bool,
}

#[derive(Subcommand)]
enum Command {
    /// Find pages on the web (needs a provider).
    Search {
        query: String,
        #[arg(short, long, default_value_t = 10)]
        limit: usize,
    },
    /// Fetch a URL, print its text, and store it locally for later search.
    Fetch { url: String },
    /// Search pages already fetched. Offline; needs no provider.
    Local {
        query: String,
        #[arg(short, long, default_value_t = 10)]
        limit: usize,
    },
    /// Serve the three operations over MCP on stdio (no daemon, no port).
    Mcp,
    /// Report what this host can do right now: provider, cache, and how to unlock what is missing.
    Doctor,
}

fn main() -> ExitCode {
    let cli = Cli::parse();
    let cache = Cache::open(cache::default_path());

    match cli.command {
        Command::Search { query, limit } => match ops::web_search(&query, limit) {
            Ok(out) => {
                if cli.json {
                    print_json(&out);
                } else if out.results.is_empty() {
                    // An empty result is only "nothing found" if the engines could answer.
                    if out.unresponsive.is_empty() {
                        println!("No results for: {query}");
                    } else {
                        println!("Nothing matched: {query}");
                        eprintln!(
                            "fleet-search: {} engine(s) could NOT answer — {} . This is not proof \
                             the query found nothing.",
                            out.unresponsive.len(),
                            out.unresponsive.join(", ")
                        );
                    }
                } else {
                    for (i, hit) in out.results.iter().enumerate() {
                        println!("{}. {}\n   {}\n   {}", i + 1, hit.title, hit.url, hit.snippet);
                    }
                    if !out.unresponsive.is_empty() {
                        eprintln!(
                            "fleet-search: {} engine(s) could not answer ({}); results are from \
                             the rest",
                            out.unresponsive.len(),
                            out.unresponsive.join(", ")
                        );
                    }
                }
                ExitCode::from(EXIT_OK)
            }
            Err(message) => {
                // "no provider" is a host-setup fact (3), anything else is a failed operation (1).
                let code = if message.contains("no search provider") {
                    EXIT_COULD_NOT_VERIFY
                } else {
                    EXIT_FAILED
                };
                eprintln!("fleet-search: {message}");
                ExitCode::from(code)
            }
        },
        Command::Fetch { url } => match ops::web_fetch(&url, &cache) {
            Ok(out) => {
                if cli.json {
                    print_json(&out);
                } else {
                    // Text on stdout (so it pipes and redirects), metadata on stderr.
                    eprintln!("{}  ({} chars, cached: {})", out.title, out.chars, out.cached);
                    println!("{}", out.text);
                }
                ExitCode::from(EXIT_OK)
            }
            Err(message) => {
                eprintln!("fleet-search: {message}");
                ExitCode::from(EXIT_FAILED)
            }
        },
        Command::Local { query, limit } => match ops::web_search_local(&query, limit, &cache) {
            Ok(out) => {
                if cli.json {
                    print_json(&out);
                } else if out.results.is_empty() {
                    println!("Nothing in the local cache matches: {query}");
                    eprintln!(
                        "fleet-search: {} page(s) cached at {}",
                        cache.count().unwrap_or(0),
                        out.cache
                    );
                } else {
                    for (i, hit) in out.results.iter().enumerate() {
                        println!("{}. {}\n   {}\n   {}", i + 1, hit.title, hit.url, hit.excerpt);
                    }
                }
                ExitCode::from(EXIT_OK)
            }
            Err(message) => {
                // An unavailable cache is a host-setup fact, not a failed search.
                let code = if message.contains("unavailable") {
                    EXIT_COULD_NOT_VERIFY
                } else {
                    EXIT_FAILED
                };
                eprintln!("fleet-search: {message}");
                ExitCode::from(code)
            }
        },
        Command::Mcp => match mcp::serve(&cache) {
            Ok(()) => ExitCode::from(EXIT_OK),
            Err(e) => {
                eprintln!("fleet-search mcp: {e}");
                ExitCode::from(EXIT_FAILED)
            }
        },
        Command::Doctor => {
            let configured = provider::configured();
            let count = cache.count().unwrap_or(0);
            if cli.json {
                print_json(&serde_json::json!({
                    "provider": configured.clone(),
                    "provider_env": provider::SEARXNG_ENV,
                    "cache_enabled": cache.enabled(),
                    "cache_path": cache.path().display().to_string(),
                    "cached_pages": count,
                    "operations": ops::OPERATIONS.iter().map(|o| serde_json::json!({
                        "name": o.name,
                        "args": o.args,
                    })).collect::<Vec<_>>(),
                    "hints": ops::hints(configured.is_some()),
                }));
            } else {
                match &configured {
                    Some(url) => println!("provider   : {url} (from {})", provider::SEARXNG_ENV),
                    None => println!("provider   : NONE — set {} to enable web_search", provider::SEARXNG_ENV),
                }
                println!(
                    "cache      : {} — {} ({} page(s), {})",
                    if cache.enabled() { "enabled" } else { "UNAVAILABLE" },
                    cache.path().display(),
                    count,
                    cache.engine()
                );
                if let Some(why) = cache.unavailable_reason() {
                    println!("cache why  : {why}");
                }
                for hint in ops::hints(configured.is_some()) {
                    println!("hint       : {hint}");
                }
            }
            ExitCode::from(EXIT_OK)
        }
    }
}

fn print_json<T: serde::Serialize>(value: &T) {
    match serde_json::to_string_pretty(value) {
        Ok(text) => println!("{text}"),
        Err(e) => eprintln!("fleet-search: could not serialise the result: {e}"),
    }
}
