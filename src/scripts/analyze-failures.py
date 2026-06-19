#!/usr/bin/env python3
"""
Analyze agent failures — cluster by pattern, identify root causes, generate reports.

Usage:
    python3 analyze-failures.py --week last
    python3 analyze-failures.py --days 7
    python3 analyze-failures.py --traces <trace-dir>
"""
import argparse
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from collections import defaultdict
from typing import Any

# Hermes tools
from hermes_tools import read_file, write_file, search_files, web_search

# Configuration
HERMES_HOME = Path.home() / ".hermes"
TRACES_DIR = HERMES_HOME / "evals" / "traces"
REPORTS_DIR = HERMES_HOME / "evals" / "reports"
LANGFUSE_DIR = Path.home() / "langfuse"


def get_failure_traces(days: int = 7) -> list[dict]:
    """Get failure traces from the past N days."""
    failures = []
    cutoff = datetime.now() - timedelta(days=days)
    
    # Scan trace files
    if TRACES_DIR.exists():
        for trace_file in TRACES_DIR.glob("*.json"):
            try:
                content = read_file(path=str(trace_file))
                trace = json.loads(content["content"])
                
                # Check if this is a failure
                result = trace.get("result", {})
                if not result.get("passed", True):
                    trace["_file"] = str(trace_file)
                    failures.append(trace)
                    
            except Exception as e:
                print(f"Error reading {trace_file}: {e}")
    
    # Also check Langfuse for failed traces (if available)
    # This would query Langfuse API for traces with low scores
    
    return failures


def extract_failure_mode(trace: dict) -> str:
    """Extract the failure mode from a trace."""
    result = trace.get("result", {})
    error = result.get("error", "")
    
    # Categorize by error pattern
    if "context" in error.lower() or "missing" in error.lower():
        return "missing_context"
    elif "duplicate" in error.lower():
        return "duplicate_detection_failed"
    elif "pattern" in error.lower() or "conflict" in error.lower():
        return "silent_pattern_blending"
    elif "complete" in error.lower() or "done" in error.lower():
        return "premature_completion"
    elif "token" in error.lower() or "overflow" in error.lower():
        return "token_overflow"
    elif "timeout" in error.lower():
        return "timeout"
    else:
        return "unknown"


def cluster_failures(failures: list[dict]) -> dict[str, list[dict]]:
    """Cluster failures by failure mode."""
    clusters = defaultdict(list)
    
    for failure in failures:
        mode = extract_failure_mode(failure)
        clusters[mode].append(failure)
    
    return dict(clusters)


def analyze_cluster(mode: str, failures: list[dict]) -> dict:
    """Analyze a cluster of failures for common patterns."""
    if not failures:
        return {"count": 0, "patterns": [], "samples": []}
    
    # Extract common features
    patterns = []
    
    # Look at task IDs
    task_ids = [f.get("task", {}).get("id", "unknown") for f in failures]
    task_id_counts = defaultdict(int)
    for tid in task_ids:
        task_id_counts[tid] += 1
    
    # Tasks with multiple failures
    problematic_tasks = [tid for tid, count in task_id_counts.items() if count >= 2]
    if problematic_tasks:
        patterns.append(f"Problematic tasks: {', '.join(problematic_tasks)}")
    
    # Look at error messages
    errors = [f.get("result", {}).get("error", "") for f in failures]
    common_words = find_common_words(errors)
    if common_words:
        patterns.append(f"Common error terms: {', '.join(common_words[:5])}")
    
    # Sample traces for manual review
    samples = failures[:3]  # First 3 for review
    
    return {
        "count": len(failures),
        "patterns": patterns,
        "samples": [s.get("_file", "unknown") for s in samples],
    }


def find_common_words(errors: list[str], min_count: int = 2) -> list[str]:
    """Find common words across error messages."""
    from collections import Counter
    
    words = []
    for error in errors:
        words.extend(error.lower().split())
    
    word_counts = Counter(words)
    # Filter to words appearing multiple times
    common = [word for word, count in word_counts.items() if count >= min_count]
    return common[:10]  # Top 10


def generate_report(clusters: dict, week: str) -> str:
    """Generate a markdown report."""
    total_failures = sum(len(failures) for failures in clusters.values())
    
    report = f"""# Weekly Failure Analysis — {week}

**Generated:** {datetime.now().strftime("%Y-%m-%d %H:%M %Z")}

## Summary

- **Total failures:** {total_failures}
- **Unique failure modes:** {len(clusters)}
- **Analysis period:** Last 7 days

## Failure Modes by Frequency

| Mode | Count | Percentage |
|------|-------|------------|
"""
    
    # Sort by count
    sorted_modes = sorted(clusters.items(), key=lambda x: len(x[1]), reverse=True)
    
    for mode, failures in sorted_modes:
        count = len(failures)
        pct = (count / total_failures * 100) if total_failures > 0 else 0
        report += f"| {mode.replace('_', ' ').title()} | {count} | {pct:.0f}% |\n"
    
    report += """
## Top Failure Modes

"""
    
    # Detail top 3 modes
    for mode, failures in sorted_modes[:3]:
        analysis = analyze_cluster(mode, failures)
        report += f"""### {mode.replace('_', ' ').title()} ({analysis['count']} failures)

**Patterns identified:**
"""
        for pattern in analysis["patterns"]:
            report += f"- {pattern}\n"
        
        report += f"""
**Sample traces for review:**
"""
        for sample in analysis["samples"]:
            report += f"- `{sample}`\n"
        
        report += "\n"
    
    report += """
## Recommended Fixes

Based on the failure patterns above:

"""
    
    # Generate recommendations based on top failure modes
    recommendations = []
    
    if "missing_context" in [m for m, _ in sorted_modes[:3]]:
        recommendations.append("1. **Add read-before-write enforcement** — require agents to read files before modifying them")
    
    if "silent_pattern_blending" in [m for m, _ in sorted_modes[:3]]:
        recommendations.append("2. **Add conflict surfacing requirement** — agents must detect and report conflicting patterns, not blend them")
    
    if "premature_completion" in [m for m, _ in sorted_modes[:3]]:
        recommendations.append("3. **Add checkpoint verification** — verify each checkpoint before marking task complete")
    
    if "duplicate_detection_failed" in [m for m, _ in sorted_modes[:3]]:
        recommendations.append("4. **Improve duplicate detection logic** — add explicit checks before creating resources")
    
    if "token_overflow" in [m for m, _ in sorted_modes[:3]]:
        recommendations.append("5. **Implement context size monitoring** — alert when approaching token limits")
    
    if not recommendations:
        recommendations.append("Review sample traces manually to identify patterns")
    
    report += "\n".join(recommendations)
    report += "\n\n"
    
    report += """
## Next Steps

1. Review sample traces for each failure mode
2. Create GitHub issues for top 3 failure patterns
3. Update agent-contract skill with new enforcement rules
4. Re-run evals after fixes to verify improvement

---

*Report generated by analyze-failures.py*
"""
    
    return report


def create_github_issues(top_modes: list[tuple[str, list[dict]]]):
    """Create GitHub issues for top failure patterns."""
    # This would use gh CLI or GitHub API to create issues
    # For now, just print what would be created
    
    print("\n📋 GitHub issues to create:")
    for mode, failures in top_modes[:3]:
        count = len(failures)
        print(f"  - [ ] Fix {mode.replace('_', ' ')} ({count} occurrences)")
        print(f"      Label: bug, agent-reliability")
        print(f"      Assignee: auto")
        print()


def main():
    parser = argparse.ArgumentParser(description="Analyze agent failure patterns")
    parser.add_argument("--week", type=str, help="Analyze last week (use 'last')")
    parser.add_argument("--days", type=int, default=7, help="Analyze last N days (default: 7)")
    parser.add_argument("--traces", type=str, help="Analyze specific trace directory")
    
    args = parser.parse_args()
    
    if args.week == "last":
        days = 7
        week_label = f"Week {datetime.now().isocalendar()[1]}, {datetime.now().year}"
    elif args.days:
        days = args.days
        week_label = f"Last {days} days"
    else:
        days = 7
        week_label = f"Week {datetime.now().isocalendar()[1]}, {datetime.now().year}"
    
    print(f"\nAnalyzing failures from the past {days} days...")
    
    # Get failure traces
    failures = get_failure_traces(days=days)
    print(f"Found {len(failures)} failures")
    
    if not failures:
        print("No failures found in the specified period")
        return
    
    # Cluster by failure mode
    clusters = cluster_failures(failures)
    print(f"Identified {len(clusters)} unique failure modes")
    
    # Generate report
    report = generate_report(clusters, week_label)
    
    # Save report
    report_filename = f"weekly-failure-{datetime.now().strftime('%Y-W%W')}.md"
    report_path = REPORTS_DIR / report_filename
    write_file(path=str(report_path), content=report)
    print(f"\n📄 Report saved: {report_path}")
    
    # Print summary
    print("\n" + "="*60)
    print("Failure Summary:")
    print("="*60)
    
    sorted_clusters = sorted(clusters.items(), key=lambda x: len(x[1]), reverse=True)
    for mode, failures in sorted_clusters[:5]:
        print(f"  {mode.replace('_', ' ').title()}: {len(failures)} failures")
    
    # Create GitHub issues for top modes
    create_github_issues(sorted_clusters[:3])
    
    print(f"\n✅ Analysis complete. Review report at: {report_path}")


if __name__ == "__main__":
    main()
