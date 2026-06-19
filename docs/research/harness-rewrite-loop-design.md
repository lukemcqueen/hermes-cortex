| Harness rewrite | skill_manage (patch/edit/create) + public-contribution (genericize → push to hermes-cortex) |

This is where hermes-cortex *exceeds* the article. The hill-climbing loop isn't one agent — it's four independent, staggered, production-hardened pipelines that each tackle a different improvement surface:

**Learnings**
• What It Improves: Bug-fix patterns, reusable fixes
• Trigger: Session FTS5 mining
• Output: Promoted lessons → lesson-database

**Skills**
• What It Improves: Reusable workflows, procedures
• Trigger: User requests + auto-digest
• Output: New/updated skills in ~/.hermes/skills/

**Memory**
• What It Improves: Working memory relevance, compression
• Trigger: Daily 4am LLM prune + Sun mechanical
• Output: MEMORY.md + brain references

**Sessions**
• What It Improves: Conversation export, PII governance
• Trigger: 2h rolling
• Output: ~/brain/{user}/conversations/

---

Where Embeddings Enhance the Hill-Climbing Loop

The article's "Engine" (LangSmith trace analyzer) is a single LLM pass over traces. Hermes-cortex has four pipelines but they're largely keyword/FTS5-based. Embeddings could add semantic signal at multiple points:

1. Learnings Pipeline — Semantic Deduplication + Clustering
Current: FTS5 text search → LLM judges relevance
Enhanced: Embed all session chunks → cluster by semantic similarity → 
          detect "same bug, different words" across sessions → auto-merge lessons
- Use web_cache/offline_knowledge embedding stack (nomic-embed-text via Ollama)
- Pre-index session chunks in gbrain; mine clusters instead of raw FTS5 hits
- Result: Fewer duplicate lessons, better cross-session pattern detection

2. Skills Pipeline — Semantic Skill Matching
Current: User requests skill → LLM evaluates fit
Enhanced: Embed skill descriptions + user request → cosine similarity → 
          suggest existing skills before creating new ones
- Index all skill SKILL.md frontmatter + body in gbrain
- Before skill_manage create, run semantic search — "this already exists as X"
- Result: Prevents skill sprawl; promotes composition over duplication

3. Memory Pipeline — Semantic Pointer Resolution
Current: Pointer pattern (MEMORY.md → /brain m <key>) requires exact key
Enhanced: Embed memory entries + brain references → semantic nearest-neighbor →
          "You asked about docker; here's the brain ref even if key was 'containers'"
- Pointer pattern already exists in SOUL.md; embeddings make it forgiving
- gbrain already does this for queries — extend to auto-resolve MEMORY.md pointers

4. Session Pipeline — Cross-User Pattern Mining
Current: Per-user export (luke/amy/shared) with PII isolation
Enhanced: Embed anonymized session summaries → cross-user semantic search →
          "Luke's Docker debugging pattern matches Amy's deployment issue"
- Strip PII → embed → shared pattern index (opt-in)
- Result: Organizational learning without PII leakage

---

Concrete Next Steps

Option A: Embedding-Enhanced Learnings Mining (Highest ROI)
# 1. Add embedding step to mine-sessions cron (02:00)
#    - Chunk session transcripts (500 tokens, 50 overlap)
#    - Embed with nomic-embed-text → store in gbrain with session_id metadata
# 2. Add clustering step to stats cron (02:30)
#    - HDBSCAN on embeddings → semantic clusters
#    - For each cluster: LLM synthesizes "this is the same root cause"
# 3. Monthly promote uses clusters, not raw FTS5 hits
Option B: Skill Semantic Index (Low Effort, High Leverage)
# 1. One-time: embed all ~/.hermes/skills/*/SKILL.md → gbrain source "skills"
# 2. Add to skill_manage create: pre-check via gbrain query --source skills
# 3. Add to cron-engineering: "Before creating cron, check skill index"
Option C: Memory Pointer Fuzzy Resolution (Native to Pattern B)
```bash
1. Already in SOUL.md: "When memory entry incomplete, query Moses brain"