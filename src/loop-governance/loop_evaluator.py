"""
Loop Evaluator — weekly analysis pipeline for self-improving loop governance.

Reads the loop-governance DB and produces:
  - Summary statistics
  - Score drift/trend detection
  - Decision accuracy analysis
  - No-progress hotspot identification
  - Threshold and weight recommendations
  - Config patch generation

Usage:
    python3 loop_evaluator.py                          # full report to stdout
    python3 loop_evaluator.py --json                   # JSON-only output
    python3 loop_evaluator.py --config-patch           # only the config patch
    python3 loop_evaluator.py --db /path/to/db.db      # custom DB path
"""

import json
import math
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

DEFAULT_DB_PATH = os.path.expanduser("~/.hermes/data/loop-governance.db")


class LoopEvaluator:
    """Analysis engine for loop governance data."""

    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from loop_db import LoopDB
        self.db = LoopDB(db_path)

    def close(self):
        self.db.close()

    # ── Statistics ───────────────────────────────────────────────────────────

    def get_weekly_stats(self, days: int = 7) -> Dict[str, Any]:
        """Aggregate statistics for the last N days."""
        row = self.db.conn.execute("""
            SELECT
                COUNT(*) AS total_cycles,
                COUNT(DISTINCT task_id) AS unique_tasks,
                COALESCE(ROUND(AVG(completeness), 2), 0) AS avg_completeness,
                COALESCE(ROUND(AVG(quality), 2), 0) AS avg_quality,
                COALESCE(ROUND(AVG(progress), 2), 0) AS avg_progress,
                COALESCE(ROUND(AVG(composite), 2), 0) AS avg_composite,
                SUM(CASE WHEN decision = 'STOP ✓' THEN 1 ELSE 0 END) AS stop_count,
                SUM(CASE WHEN decision LIKE 'LOOP%' THEN 1 ELSE 0 END) AS loop_count,
                SUM(CASE WHEN decision LIKE 'MOVE ON%' THEN 1 ELSE 0 END) AS move_on_count,
                SUM(CASE WHEN decision LIKE 'STOP ✗%' THEN 1 ELSE 0 END) AS hard_fail_count,
                SUM(CASE WHEN no_progress = 1 THEN 1 ELSE 0 END) AS no_progress_count,
                SUM(CASE WHEN user_overrode IS NOT NULL THEN 1 ELSE 0 END) AS feedback_count,
                ROUND(AVG(cycle_num), 1) AS avg_cycles_per_task
            FROM loop_cycles
            WHERE timestamp >= datetime('now', '-' || ? || ' days')
        """, (days,)).fetchone()
        return dict(row)

    def get_decision_breakdown(self, days: int = 7) -> Dict[str, int]:
        """Count of each decision type."""
        rows = self.db.conn.execute("""
            SELECT
                CASE
                    WHEN decision = 'STOP ✓' THEN 'STOP'
                    WHEN decision LIKE 'LOOP%' THEN 'LOOP'
                    WHEN decision LIKE 'MOVE ON%' THEN 'MOVE ON'
                    WHEN decision LIKE 'STOP ✗%' THEN 'HARD FAIL'
                    ELSE 'OTHER'
                END as category,
                COUNT(*) AS count
            FROM loop_cycles
            WHERE timestamp >= datetime('now', '-' || ? || ' days')
            GROUP BY category
            ORDER BY count DESC
        """, (days,)).fetchall()
        return {r["category"]: r["count"] for r in rows}

    # ── Score Trend Detection ────────────────────────────────────────────────

    def get_score_trends(self, days: int = 30) -> List[Dict[str, Any]]:
        """Detect drift in each score dimension by comparing first vs second half."""
        results = []
        for dim in ["completeness", "quality", "progress", "composite"]:
            row = self.db.conn.execute(f"""
                SELECT
                    CASE WHEN rn <= total/2.0 THEN 'first_half' ELSE 'second_half' END AS period,
                    ROUND(AVG({dim}), 2) AS avg_score
                FROM (
                    SELECT {dim}, ROW_NUMBER() OVER (ORDER BY id) AS rn,
                           COUNT(*) OVER () AS total
                    FROM loop_cycles
                    WHERE timestamp >= datetime('now', '-' || ? || ' days')
                      AND {dim} IS NOT NULL
                )
                GROUP BY period
                ORDER BY period
            """, (days,)).fetchall()

            if len(row) < 2:
                continue

            first = row[0]["avg_score"]
            second = row[1]["avg_score"]
            diff = round(second - first, 2)

            if abs(diff) < 0.3:
                direction = "stable"
            elif diff > 0:
                direction = "up"
            else:
                direction = "down"

            results.append({
                "dimension": dim,
                "first_half_avg": first,
                "second_half_avg": second,
                "diff": diff,
                "direction": direction,
            })

        return results

    # ── No-Progress Hotspots ────────────────────────────────────────────────

    def get_no_progress_hotspots(self, days: int = 30, limit: int = 5) -> List[Dict]:
        """Tasks with the most no-progress cycles."""
        rows = self.db.conn.execute("""
            SELECT task_id, COUNT(*) AS np_count,
                   ROUND(AVG(composite), 2) AS avg_composite
            FROM loop_cycles
            WHERE no_progress = 1
              AND timestamp >= datetime('now', '-' || ? || ' days')
            GROUP BY task_id
            ORDER BY np_count DESC
            LIMIT ?
        """, (days, limit)).fetchall()
        return [dict(r) for r in rows]

    def get_spinning_tasks(self, days: int = 30) -> List[Dict]:
        """Tasks with 3+ consecutive no-progress cycles."""
        # This requires iterating per-task
        task_rows = self.db.conn.execute("""
            SELECT DISTINCT task_id FROM loop_cycles
            WHERE timestamp >= datetime('now', '-' || ? || ' days')
        """, (days,)).fetchall()

        spinning = []
        for (task_id,) in task_rows:
            streak = self.db.get_no_progress_streak(task_id)
            if streak >= 3:
                spinning.append({"task_id": task_id, "consecutive_np": streak})

        return sorted(spinning, key=lambda x: x["consecutive_np"], reverse=True)

    # ── Decision Accuracy ───────────────────────────────────────────────────

    def get_decision_accuracy(self) -> Dict[str, Any]:
        """How often user feedback agreed with the loop decision."""
        rows = self.db.conn.execute("""
            SELECT decision, user_overrode, COUNT(*) AS count
            FROM loop_cycles
            WHERE user_overrode IS NOT NULL
            GROUP BY decision, user_overrode
        """).fetchall()

        total = sum(r["count"] for r in rows)
        if total == 0:
            return {"total_feedback": 0, "accuracy_pct": 0, "breakdown": []}

        # user_overrode = 0 means accepted (decision was correct)
        # user_overrode = 1 means overrode (decision was wrong)
        correct = sum(r["count"] for r in rows if r["user_overrode"] == 0)
        incorrect = sum(r["count"] for r in rows if r["user_overrode"] == 1)

        return {
            "total_feedback": total,
            "correct": correct,
            "incorrect": incorrect,
            "accuracy_pct": round(correct / total * 100, 1),
            "breakdown": [dict(r) for r in rows],
        }

    # ── Recommendations ──────────────────────────────────────────────────────

    def get_threshold_recommendations(self) -> List[Dict[str, Any]]:
        """Analyze user feedback to recommend threshold adjustments.

        Returns structured recommendations with 'proposed_value' for auto-apply.
        """
        recs = []

        # Check STOP threshold (default 8.0)
        overridden_stops = self.db.conn.execute("""
            SELECT composite, user_overrode
            FROM loop_cycles
            WHERE decision = 'STOP ✓' AND user_overrode = 1
        """).fetchall()

        if overridden_stops:
            avg_composite = round(sum(r["composite"] for r in overridden_stops) / len(overridden_stops), 2)
            proposed = round(min(9.0, avg_composite + 0.5), 1)
            recs.append({
                "threshold": "STOP (composite ≥ 8.0)",
                "config_key": "stop",
                "issue": f"{len(overridden_stops)} STOP decisions were overridden by user",
                "avg_composite_when_overridden": avg_composite,
                "proposed_value": proposed,
                "recommendation": f"Consider raising STOP threshold to {proposed} "
                                  f"or adding quality gate (quality ≥ 6.0)",
                "confidence": "medium" if len(overridden_stops) >= 3 else "low",
            })

        # Check MOVE ON threshold (default 3.0)
        moved_on_but_failed = self.db.conn.execute("""
            SELECT composite, user_overrode
            FROM loop_cycles
            WHERE decision LIKE 'MOVE ON%' AND user_overrode = 1
        """).fetchall()

        if moved_on_but_failed:
            avg_comp = round(sum(r["composite"] for r in moved_on_but_failed) / len(moved_on_but_failed), 2)
            proposed = round(max(2.0, avg_comp - 0.5), 1)
            recs.append({
                "threshold": "MOVE ON (composite ≥ 3.0)",
                "config_key": "move_on",
                "issue": f"{len(moved_on_but_failed)} MOVE ON decisions were overridden (should have LOOPed)",
                "avg_composite_when_overridden": avg_comp,
                "proposed_value": proposed,
                "recommendation": f"Consider lowering MOVE ON threshold to {proposed} "
                                  f"to keep looping on borderline cases",
                "confidence": "medium" if len(moved_on_but_failed) >= 3 else "low",
            })

        # Check for no-progress threshold
        np_rows = self.db.conn.execute("""
            SELECT COUNT(*) as total,
                   ROUND(AVG(composite), 2) as avg_composite
            FROM loop_cycles
            WHERE no_progress = 1
        """).fetchone()

        if np_rows and np_rows["total"] >= 5:
            recs.append({
                "threshold": "no-progress (progress < 2.0)",
                "config_key": "no_progress_limit",
                "issue": f"{np_rows['total']} no-progress cycles detected",
                "avg_composite_when_overridden": np_rows["avg_composite"],
                "proposed_value": 2,
                "recommendation": "Tighten no-progress limit from 3 to 2 consecutive",
                "confidence": "medium",
            })

        return recs

    def get_weight_recommendations(self) -> List[Dict[str, Any]]:
        """Analyze which score dimensions correlate best with user satisfaction."""
        rows = self.db.conn.execute("""
            SELECT completeness, quality, progress, composite,
                   CASE WHEN user_overrode = 0 THEN 1 ELSE 0 END AS accepted
            FROM loop_cycles
            WHERE user_overrode IS NOT NULL
        """).fetchall()

        if len(rows) < 5:
            return []  # not enough data

        # Simple correlation: for each dimension, compare avg when accepted vs rejected
        dims = ["completeness", "quality", "progress"]
        recs = []
        current_weights = {"completeness": 0.40, "quality": 0.30, "progress": 0.30}

        for dim in dims:
            accepted_vals = [r[dim] for r in rows if r["accepted"] == 1]
            rejected_vals = [r[dim] for r in rows if r["accepted"] == 0]

            if not accepted_vals or not rejected_vals:
                continue

            avg_acc = sum(accepted_vals) / len(accepted_vals)
            avg_rej = sum(rejected_vals) / len(rejected_vals)
            delta = round(avg_acc - avg_rej, 2)

            # The bigger the delta, the more that dimension predicts acceptance
            # Suggest weight adjustment proportional to delta
            if abs(delta) > 0.5:
                adjustment = round(delta * 0.03, 2)  # scale delta to weight change
                new_weight = round(min(0.60, max(0.10, current_weights[dim] + adjustment)), 2)
                recs.append({
                    "dimension": dim,
                    "current_weight": current_weights[dim],
                    "recommended_weight": new_weight,
                    "delta_when_accepted": delta,
                    "rationale": f"User acceptance delta: {delta:+.2f}. "
                                 f"{'Higher scores in this dimension correlate with acceptance' if delta > 0 else 'Lower scores correlate with acceptance'}",
                    "confidence": "low" if len(rows) < 15 else "medium",
                })

        return recs

    # ── Report Generation ───────────────────────────────────────────────────

    def generate_report(self, days: int = 7) -> str:
        """Generate a full evaluation report as markdown."""
        stats = self.get_weekly_stats(days)
        breakdown = self.get_decision_breakdown(days)
        trends = self.get_score_trends(days)
        hotspots = self.get_no_progress_hotspots(days)
        spinning = self.get_spinning_tasks(days)
        accuracy = self.get_decision_accuracy()
        threshold_recs = self.get_threshold_recommendations()
        weight_recs = self.get_weight_recommendations()

        period = f"last {days} days" if days != 365 else "all time"

        lines = []
        lines.append(f"# Evaluation Report — {period}")
        lines.append(f"**Generated:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
        lines.append("")

        # ── Summary ──
        lines.append("## Summary")
        lines.append(f"| Metric | Value |")
        lines.append(f"|--------|-------|")
        lines.append(f"| Total cycles | {stats['total_cycles']} |")
        lines.append(f"| Unique tasks | {stats['unique_tasks']} |")
        lines.append(f"| Avg cycles per task | {stats['avg_cycles_per_task']} |")
        lines.append(f"| Avg composite score | {stats['avg_composite']} /10 |")
        lines.append(f"| Avg completeness | {stats['avg_completeness']} /10 |")
        lines.append(f"| Avg quality | {stats['avg_quality']} /10 |")
        lines.append(f"| Avg progress | {stats['avg_progress']} /10 |")
        lines.append(f"| No-progress cycles | {stats['no_progress_count']} |")
        lines.append(f"| User feedback collected | {stats['feedback_count']} |")
        lines.append("")

        # ── Decision Distribution ──
        lines.append("## Decision Distribution")
        lines.append(f"| Decision | Count |")
        lines.append(f"|----------|-------|")
        for dec, count in sorted(breakdown.items(), key=lambda x: x[1], reverse=True):
            lines.append(f"| {dec} | {count} |")
        lines.append("")

        # ── Score Trends ──
        lines.append("## Score Trends")
        if trends:
            lines.append(f"| Dimension | First Half | Second Half | Diff | Direction |")
            lines.append(f"|-----------|-----------|------------|------|-----------|")
            for t in trends:
                arrow = "↑" if t["direction"] == "up" else "↓" if t["direction"] == "down" else "→"
                lines.append(f"| {t['dimension']} | {t['first_half_avg']} | {t['second_half_avg']} | {t['diff']:+.2f} | {arrow} {t['direction']} |")
        else:
            lines.append("_Not enough data for trend analysis._")
        lines.append("")

        # ── No-Progress Hotspots ──
        lines.append("## No-Progress Hotspots")
        if hotspots:
            lines.append(f"| Task | No-Progress Cycles | Avg Composite |")
            lines.append(f"|------|-------------------:|:-------------:|")
            for h in hotspots:
                lines.append(f"| `{h['task_id']}` | {h['np_count']} | {h['avg_composite']} |")
        else:
            lines.append("_No no-progress hotspots detected._")

        if spinning:
            lines.append("")
            lines.append("### ⚠ Spinning Tasks (3+ consecutive no-progress)")
            for s in spinning:
                lines.append(f"- `{s['task_id']}` — {s['consecutive_np']} consecutive")
        lines.append("")

        # ── Decision Accuracy ──
        lines.append("## Decision Accuracy")
        if accuracy["total_feedback"] > 0:
            lines.append(f"**{accuracy['accuracy_pct']}%** correct "
                         f"({accuracy['correct']}/{accuracy['total_feedback']} decisions)")
            if accuracy["breakdown"]:
                lines.append("")
                lines.append("| Decision | User Accepted | User Overrode |")
                lines.append("|----------|:------------:|:-------------:|")
                for b in accuracy["breakdown"]:
                    label = "Accepted" if b["user_overrode"] == 0 else "Overrode"
                    lines.append(f"| {b['decision'][:20]} | {label} | {b['count']} |")
        else:
            lines.append("_No user feedback recorded yet. User feedback is the ground-truth label for meta-learning._")
        lines.append("")

        # ── Recommendations ──
        lines.append("## Recommendations")

        if threshold_recs:
            lines.append("### Threshold Adjustments")
            for r in threshold_recs:
                lines.append(f"- **{r['threshold']}:** {r['recommendation']} "
                             f"(confidence: {r['confidence']})")
            lines.append("")

        if weight_recs:
            lines.append("### Weight Adjustments")
            lines.append(f"| Dimension | Current | Recommended | Rationale |")
            lines.append(f"|-----------|:-------:|:-----------:|-----------|")
            for r in weight_recs:
                lines.append(f"| {r['dimension']} | {r['current_weight']:.0%} | "
                             f"{r['recommended_weight']:.0%} | {r['rationale'][:60]}... |")
            lines.append("")

        if not threshold_recs and not weight_recs:
            lines.append("_No recommendations available. Need more data (especially user feedback)._")
            lines.append("")

        # ── Config Patch ──
        lines.append("## Config Patch Preview")
        patch = self.generate_config_patch()
        if patch["changes"]:
            lines.append(f"```json")
            lines.append(json.dumps(patch, indent=2))
            lines.append(f"```")
        else:
            lines.append("_No changes recommended._")
        lines.append("")

        return "\n".join(lines)

    def generate_config_patch(self) -> Dict[str, Any]:
        """Generate a config patch JSON with recommended changes.

        Output is structured for auto-apply:
        {
            "changes": {
                "thresholds": {"stop": 8.5, "move_on": 2.5},
                "weights": {"completeness": 0.45},
                "auto_apply": {"no_progress_limit": 2}
            },
            "confidence": 0.65,
            "requires_review": false
        }
        """
        changes = {"thresholds": {}, "weights": {}, "auto_apply": {}}
        rationale = []
        confidence = 0.0
        evidence_count = 0

        # Structured threshold recommendations (with config_key + proposed_value)
        threshold_recs = self.get_threshold_recommendations()
        for r in threshold_recs:
            ck = r.get("config_key", "")
            pv = r.get("proposed_value")
            conf = r.get("confidence", "low")

            if ck and pv is not None:
                if ck == "stop":
                    changes["thresholds"]["stop"] = pv
                    rationale.append(r.get("issue", ""))
                    evidence_count += 1
                    confidence += 0.3 if conf == "medium" else 0.15
                elif ck == "move_on":
                    changes["thresholds"]["move_on"] = pv
                    rationale.append(r.get("issue", ""))
                    evidence_count += 1
                    confidence += 0.3 if conf == "medium" else 0.15
                elif ck == "no_progress_limit":
                    changes["auto_apply"]["no_progress_limit"] = pv
                    rationale.append(r.get("issue", ""))
                    evidence_count += 1
                    confidence += 0.3 if conf == "medium" else 0.15

        # Structured weight recommendations (with recommended_weight)
        weight_recs = self.get_weight_recommendations()
        for r in weight_recs:
            w = r.get("recommended_weight")
            if w is not None:
                changes["weights"][r["dimension"]] = w
                rationale.append(f"{r['dimension']}: {r.get('rationale', '')[:80]}")
                evidence_count += 1
                confidence += 0.4 if r.get("confidence") == "medium" else 0.2

        avg_confidence = round(confidence / max(evidence_count, 1), 2)
        requires_review = avg_confidence < 0.7 or evidence_count < 2

        return {
            "schema_version": 2,
            "generated": datetime.now(timezone.utc).isoformat(),
            "changes": changes,
            "rationale": "; ".join(rationale),
            "confidence": avg_confidence,
            "requires_review": requires_review,
        }


# ── CLI ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    db_path = DEFAULT_DB_PATH
    days = 7
    output_format = "report"

    args = sys.argv[1:]
    for i, arg in enumerate(args):
        if arg == "--db" and i + 1 < len(args):
            db_path = os.path.expanduser(args[i + 1])
        elif arg == "--days" and i + 1 < len(args):
            days = int(args[i + 1])
        elif arg == "--json":
            output_format = "json"
        elif arg == "--config-patch":
            output_format = "config_patch"

    ev = LoopEvaluator(db_path)

    if output_format == "json":
        result = {
            "stats": ev.get_weekly_stats(days),
            "breakdown": ev.get_decision_breakdown(days),
            "trends": ev.get_score_trends(days),
            "hotspots": ev.get_no_progress_hotspots(days),
            "spinning": ev.get_spinning_tasks(days),
            "accuracy": ev.get_decision_accuracy(),
            "threshold_recs": ev.get_threshold_recommendations(),
            "weight_recs": ev.get_weight_recommendations(),
            "config_patch": ev.generate_config_patch(),
        }
        print(json.dumps(result, indent=2))

    elif output_format == "config_patch":
        print(json.dumps(ev.generate_config_patch(), indent=2))

    else:
        print(ev.generate_report(days=days))

    ev.close()
