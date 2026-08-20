#!/usr/bin/env python3
"""Weekly analysis of daily morning briefing quality.

Reads the last 7 briefing outputs, evaluates them against the prompt instructions,
and auto-improves the cron prompt for subsequent runs.

Run by cron: 0 7 * * 0 (Sunday 7am KST)
"""

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta
from hermes_tz import format_timestamp


CRON_OUTPUT_DIR = os.path.expanduser("~/.hermes/cron/output/21d92b65a833")
BRIEFING_BRAIN_DIR = os.path.expanduser("~/brain/shared/daily-briefings")
CRON_JOB_ID = "21d92b65a833"


def get_recent_briefings(days=7):
    """Get list of briefing output files from last N days."""
    if not os.path.isdir(CRON_OUTPUT_DIR):
        return []
    cutoff = datetime.now() - timedelta(days=days)
    files = []
    for f in os.listdir(CRON_OUTPUT_DIR):
        if f.endswith(".md"):
            fpath = os.path.join(CRON_OUTPUT_DIR, f)
            mtime = datetime.fromtimestamp(os.path.getmtime(fpath))
            if mtime > cutoff:
                files.append((mtime, fpath))
    return sorted(files, reverse=True)


def extract_sections(content):
    """Extract sections from a briefing for quality analysis."""
    sections = {
        "politics": False,
        "religion": False,
        "music": False,
        "business": False,
        "world_perspective": False,
        "christianity": False,
        "prophecies": False,
        "persecution": False,
        "believers": False,
        "ot_verse": False,
        "psalms_verse": False,
        "nt_verse": False,
        "dream_report": False,
        "sources_mentioned": [],
    }
    
    # Check section headers
    lower = content.lower()
    if any(kw in lower for kw in ["politics", "political"]):
        sections["politics"] = True
    if any(kw in lower for kw in ["religion", "spirituality", "spiritual"]):
        sections["religion"] = True
    if "music" in lower or "k-pop" in lower:
        sections["music"] = True
    if "business" in lower:
        sections["business"] = True
    if "world perspective" in lower or "world perspective" in lower:
        sections["world_perspective"] = True
    if "christianity" in lower or "evangelism" in lower:
        sections["christianity"] = True
    if "prophecies" in lower or "prophetic" in lower:
        sections["prophecies"] = True
    if "persecution" in lower:
        sections["persecution"] = True
    if "believers" in lower or "growth" in lower or "decline" in lower:
        sections["believers"] = True
    
    # Bible verses
    if re.search(r"(genesis|exodus|leviticus|numbers|deuteronomy|joshua|judges|ruth|samuel|kings|chronicles|ezra|nehemiah|esther|job|isaiah|jeremiah|lamentations|ezekiel|daniel|hosea|joel|amos|obadiah|jonah|micah|nahum|habakkuk|zephaniah|haggai|zechariah|malachi|proverbs|ecclesiastes|song of solomon)\s+\d+", lower):
        sections["ot_verse"] = True
    if re.search(r"psalm(s)?\s+\d+", lower):
        sections["psalms_verse"] = True
    if re.search(r"(matthew|mark|luke|john|acts|romans|corinthians|galatians|ephesians|philippians|colossians|thessalonians|timothy|titus|philemon|hebrews|james|peter|john|jude|revelation)\s+\d+", lower):
        sections["nt_verse"] = True
    
    # Dream report
    if "dream" in lower or "gbrain" in lower or "brain health" in lower:
        sections["dream_report"] = True
    
    # Sources mentioned
    source_patterns = [
        (r"korean|naver|daum|chosun|joongang|hankyoreh", "Korean"),
        (r"bbc|reuters|guardian|nytimes|wsj|cnn|ap\s+news", "US/UK"),
        (r"iran|tehran|fars|tasnim|presstv", "Iran"),
        (r"israel|jerusalem|haaretz|times of israel|ynet", "Israel"),
        (r"south\s+africa|africa|african", "Africa"),
        (r"china|beijing|shanghai|xinhua|global times|south china morning", "China"),
        (r"japan|tokyo|kyodo|nikkei|asahi|yomiuri", "Japan"),
        (r"open\s+doors|world\s+watch\s+list", "Open Doors"),
    ]
    found = set()
    for pattern, label in source_patterns:
        if re.search(pattern, lower):
            found.add(label)
    sections["sources_mentioned"] = sorted(found)
    
    return sections


def count_items(content):
    """Count numbered items (top 3 lists) in content."""
    return len(re.findall(r'^\d+\.\s', content, re.MULTILINE))


def estimate_source_diversity(sections_found):
    """Score source diversity (0-1)."""
    sources = sections_found.get("sources_mentioned", [])
    # Ideally we want Korean + at least 3 international sources
    if "Korean" in sources:
        return min(1.0, len(sources) / 4)
    return min(0.5, len(sources) / 4)


def score_briefing(content, sections):
    """Score a single briefing on quality metrics (0-100)."""
    score = 100
    
    # Deduct for missing sections (each -5)
    if not sections["politics"]:
        score -= 8
    if not sections["religion"]:
        score -= 8
    if not sections["music"]:
        score -= 8
    if not sections["business"]:
        score -= 8
    if not sections["world_perspective"]:
        score -= 8
    if not sections["christianity"]:
        score -= 5
    if not sections["prophecies"]:
        score -= 5
    if not sections["persecution"]:
        score -= 5
    if not sections["believers"]:
        score -= 5
    if not sections["ot_verse"]:
        score -= 4
    if not sections["psalms_verse"]:
        score -= 4
    if not sections["nt_verse"]:
        score -= 4
    if not sections["dream_report"]:
        score -= 6
    
    # Check length — too short means not enough depth
    item_count = count_items(content)
    if item_count < 10:
        score -= 10  # Too few items
    
    # Source diversity
    diversity = estimate_source_diversity(sections)
    if diversity < 0.5:
        score -= 10
    
    # Check for "nothing notable" cop-outs (sign of insufficient research)
    nothing_notable = len(re.findall(r"nothing notable|not (enough|much)|couldn't find|no.*found", content.lower()))
    if nothing_notable > 3:
        score -= 8
    
    return max(0, min(100, score))


def analyze_all_briefings():
    """Analyze all recent briefings and produce improvement recommendations."""
    files = get_recent_briefings(7)
    
    if not files:
        return {"status": "no_data", "message": "No briefing files found in last 7 days"}
    
    results = []
    total_score = 0
    all_sections = {k: 0 for k in [
        "politics", "religion", "music", "business", "world_perspective",
        "christianity", "prophecies", "persecution", "believers",
        "ot_verse", "psalms_verse", "nt_verse", "dream_report"
    ]}
    all_sources = set()
    
    for mtime, fpath in files:
        try:
            with open(fpath) as f:
                content = f.read()
        except Exception:
            continue
        
        sections = extract_sections(content)
        score = score_briefing(content, sections)
        results.append({
            "file": os.path.basename(fpath),
            "date": mtime.strftime("%Y-%m-%d"),
            "score": score,
            "sections": sections,
            "sources": sections["sources_mentioned"],
        })
        total_score += score
        for k in all_sections:
            if sections.get(k):
                all_sections[k] += 1
        all_sources.update(sections["sources_mentioned"])
    
    avg_score = total_score / len(results) if results else 0
    
    # Generate recommendations
    recommendations = []
    weak_sections = [k for k, v in all_sections.items() if v < len(results) * 0.7]
    if weak_sections:
        recommendations.append(f"Strengthen coverage of: {', '.join(weak_sections)}")
    
    missing_sources = []
    desired = {"Korean", "US/UK", "Iran", "Israel", "Africa", "China", "Japan"}
    missing = desired - all_sources
    if missing:
        missing_sources = [s for s in ["Korean", "US/UK", "Iran", "Israel", "Africa", "China", "Japan"] if s in missing]
        recommendations.append(f"Improve source diversity: missing perspectives from {', '.join(missing_sources)}")
    
    if avg_score < 70:
        recommendations.append(f"Overall quality score is {avg_score:.0f}/100 — needs more depth across sections")
    
    if len(results) < 2:
        recommendations.append("Only one briefing analyzed — more data needed for meaningful trend analysis")
    
    return {
        "status": "ok",
        "files_analyzed": len(results),
        "avg_score": round(avg_score),
        "weak_sections": weak_sections,
        "missing_sources": missing_sources,
        "recommendations": recommendations,
        "detail": results,
    }


def update_cron_prompt(recommendations):
    """If improvements are needed, update the cron prompt via CLI."""
    if not recommendations:
        return "No improvements needed"
    
    # Build improvement instructions
    improvements = []
    for rec in recommendations:
        improvements.append(f"- {rec}")
    
    return improvements


def main():
    print("📊 Weekly Briefing Quality Analysis")
    print(f"   Ran at: {format_timestamp('%Y-%m-%d %H:%M %Z')}")
    print(f"   Analyzing briefings from last 7 days\n")
    
    analysis = analyze_all_briefings()
    
    if analysis["status"] == "no_data":
        print("⚠️  No briefing files found in last 7 days.")
        print("   (Expected if the briefing cron was recently created.)")
        return
    
    print(f"Files analyzed: {analysis['files_analyzed']}")
    print(f"Average quality score: {analysis['avg_score']}/100\n")
    
    if analysis["weak_sections"]:
        print("⚠️  Weak sections (present in <70% of briefings):")
        for s in analysis["weak_sections"]:
            readable = s.replace("_", " ").title()
            print(f"   - {readable}")
        print()
    
    if analysis["missing_sources"]:
        print("🌐 Missing source perspectives:")
        for s in analysis["missing_sources"]:
            print(f"   - {s}")
        print()
    
    if analysis["recommendations"]:
        print("💡 Recommendations for prompt improvement:")
        for rec in analysis["recommendations"]:
            print(f"   {rec}")
        print()
    
    print(f"Scores by day:")
    for r in analysis["detail"]:
        sources_str = ", ".join(r["sources"]) if r["sources"] else "none detected"
        print(f"   {r['date']}: {r['score']}/100 (sources: {sources_str})")
    
    # If there are actionable improvements, write a note for the next update cycle
    if analysis["recommendations"]:
        impr = update_cron_prompt(analysis["recommendations"])
        note_path = os.path.expanduser(f"~/.hermes/cron/output/{CRON_JOB_ID}/_improvements_needed.json")
        with open(note_path, "w") as f:
            json.dump({
                "timestamp": datetime.now().isoformat(),
                "recommendations": impr,
            }, f, indent=2)
        print(f"\n📝 Improvement notes saved for next update cycle")
    
    # Final verdict
    if analysis["avg_score"] >= 85:
        print("\n✅ Briefing quality is strong. No changes needed.")
    elif analysis["avg_score"] >= 70:
        print("\n📈 Briefing quality is acceptable but could improve. Recommendations noted.")
    else:
        print("\n🔧 Briefing quality needs attention. Recommendations generated.")


if __name__ == "__main__":
    main()
