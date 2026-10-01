Yes — and that changes my recommendation.

If your #1 requirement is:

> **“I want a boring, old, solid foundation that can sit unchanged for a year and keep working.”**

then **Pi upstream is not the answer in its current form**. Its release philosophy explicitly permits breaking API changes in minor releases, and it is evolving fast. ([GitHub][1])

OpenHands is more disciplined about compatibility, but it is also a much larger moving system, and even its current UI/architecture transition is still described as beta with stability work ongoing. ([GitHub][2])

So I would change course:

# Build the stable core yourselves.

Not an entire coding agent from scratch. Build a **small, frozen Cortex runtime contract** whose whole purpose is to *not change*.

The architecture I would aim for is:

```text
                    CORTEX CORE
             versioned extremely slowly
          ───────────────────────────────
          Task state machine
          Queue / leases
          Worker supervision
          Workspace isolation
          Tool gateway
          Governance
          Checkpoints
          Retry / recovery
          Cost accounting
          Audit log
          Observability contracts
          ───────────────────────────────
                    │
              Worker ABI v1
                    │
        ┌───────────┼───────────┐
        │           │           │
      Pi vX      Claude      OpenHands
      pinned      CLI         pinned
        │           │           │
        └──────── disposable ────┘
```

The critical distinction is:

**Cortex Core should have essentially zero dependency on Pi, Hermes, Claude, OpenHands, Qwen, etc.**

Those become peripheral drivers.

## Think Linux kernel, not npm app

Your frustration is partly architectural.

Hermes Cortex currently inherits too much behavior from a project whose owners are still actively inventing Hermes.

If the upstream project decides:

> “We improved how sessions work.”

you inherit their improvement *and their bugs*.

If they redesign tools:

> Cortex changes.

If they redesign memory:

> Cortex changes.

If they change provider routing:

> Cortex changes.

That's exactly backwards for infrastructure.

You want:

> **Cortex defines reality. Everything else adapts to Cortex.**

That means a three-year-old worker could theoretically still connect.

---

# I would make stability an explicit product feature

Have a concept like:

### Cortex Runtime ABI 1.0

And commit to something unusually conservative:

**ABI 1.0 never breaks.**

Seriously.

Instead of constantly improving the interface:

```text
Cortex Worker ABI 1.0
2026–2029
```

If you eventually need something better:

```text
ABI 2.0
```

But Cortex still understands ABI 1.

This is what mature infrastructure does.

---

# What actually belongs in this frozen layer?

Surprisingly little.

I'd keep it brutally small.

A task:

```json
{
  "task_id": "abc123",
  "objective": "Fix race condition",
  "workspace": "...",
  "permissions": "...",
  "budget": "...",
  "model_policy": "...",
  "verification_policy": "..."
}
```

Worker events:

```text
WORKER_STARTED
MODEL_REQUEST_STARTED
MODEL_REQUEST_FINISHED
TOOL_REQUESTED
TOOL_STARTED
TOOL_FINISHED
PROGRESS
CHECKPOINT
RESULT
FAILED
STOPPED
```

Worker operations:

```text
start
send
cancel
checkpoint
status
kill
```

That's roughly it.

Do not let it become a 300-method framework.

---

# Even model interaction doesn't need to be part of Cortex Core

This is important.

I earlier suggested keeping Pi's provider abstraction.

I'd now isolate that further too.

Have:

```text
Cortex Core
     │
Worker process
     │
LLM adapter
```

Then a Pi worker can use Pi's model stack.

A Claude worker uses Claude Code.

Another lightweight worker might use LiteLLM.

Another could use OpenAI directly.

Another could run llama.cpp.

**Cortex does not care.**

Now Pi can break its OpenAI provider tomorrow and your orchestration system remains completely healthy.

One worker class is degraded.

That is a very different failure.

---

# Your stable system shouldn't know what a “Pi session” is

Or:

```text
Hermes session
Claude conversation
OpenHands conversation
Qwen subagent
```

Those are implementation details.

Cortex should know:

```text
task_id
attempt_id
worker_id
workspace_id
checkpoint_id
lease_id
```

That vocabulary is yours.

It doesn't change because somebody on GitHub had a new architectural idea.

---

# I would also stop chasing updates

This is probably the operational change you'll appreciate the most.

You do **not** need the latest agent harness.

For infrastructure, “latest” is often a liability.

I would deliberately run something like:

```text
Cortex Pi Worker
Upstream base: Pi 0.84.x
Cortex patch: 1.3.7
Status: CERTIFIED
```

And six months later:

```text
Pi upstream: 0.97
Cortex production: still 0.84.x
```

Who cares?

If 0.84 reliably sends prompts, executes tools and returns results, **leave it alone**.

Security issue?

Patch that security issue.

Provider API changed?

Patch the provider.

Compelling capability?

Backport it.

Otherwise:

### Don't touch it.

---

# This is where a fork actually makes sense

Forks get a bad reputation because people create permanent giant diverging forks.

I wouldn't do that.

I'd make a **maintenance fork**, not an innovation fork.

Its philosophy:

> No new features unless Cortex actually needs them.

Example:

```text
cortex-pi
```

Rules:

* Pin all dependencies.
* No automatic dependency upgrades.
* No Renovate auto-merges.
* No upstream merges.
* No cosmetic refactors.
* No architecture rewrites.
* Security patches only by default.
* Bug fixes require regression tests.
* Provider updates individually cherry-picked.
* New capability requires a concrete Cortex use case.
* Every release must pass the Cortex compatibility suite.

That could sit at the same underlying Pi commit for **18 months**.

That's good.

---

# And I would use semantic versions differently

Your versions:

```text
Cortex Core 1.4.13
```

`1.x` API remains compatible.

Your runtime drivers:

```text
cortex-worker-pi 1.9
cortex-worker-claude 1.4
cortex-worker-openhands 1.1
```

Completely independent.

So this:

```text
Pi worker broken
```

doesn't mean:

```text
Cortex upgrade
```

That's a huge difference.

---

# OpenHands loses even more appeal under this requirement

OpenHands has better formal compatibility discipline than Pi. That's real.

But you're optimizing for:

> **minimal change surface**

not merely:

> backward-compatible APIs.

OpenHands has far more subsystems that can change independently.

There are still current enterprise issues around configuration, Kubernetes runtime URLs, persisted settings and integration behavior. ([GitHub][3])

And there have been self-hosted issues where internal assumptions about workspace/repository layout broke setup hooks. ([GitHub][4])

That's the type of issue I'd rather completely eliminate by making your execution model tiny.

---

# There is actually an even more conservative alternative to Pi

This is worth considering seriously:

## Don't use a “coding agent” as your foundational library at all.

Build a **very small Cortex worker**.

Conceptually it's only:

```python
while not finished:
    response = llm(messages, tools)

    if response.tool_call:
        result = cortex_tools.execute(response.tool_call)
        messages.append(result)
    else:
        finished = True
```

Obviously production code needs streaming, retries, tool-call normalization, context management, etc.

But the actual agent loop is **not sophisticated**.

Pi's value is all the stuff around this loop.

The question becomes:

> Is that value worth inheriting another evolving framework?

For your requirements, I'm increasingly leaning:

### **Maybe not.**

---

# What I'd seriously evaluate now

Three possibilities:

| Architecture                         | Stability | Maintenance | Flexibility | My view             |
| ------------------------------------ | --------: | ----------: | ----------: | ------------------- |
| Cortex → upstream Pi                 |         5 |       **9** |          10 | ❌ repeats Hermes    |
| Cortex → frozen Pi fork              |   **9.5** |           8 |      **10** | ✅ excellent         |
| **Cortex → own tiny worker runtime** |    **10** |         6.5 |      **10** | 🏆 potentially best |

And this is where I'd now spend our energy.

---

# Building your own might actually be smaller than it sounds

You are **not** rebuilding Claude Code.

You're not writing an IDE.

You're not writing an LLM.

You're not implementing VS Code.

You're not even necessarily implementing model APIs yourself.

Use mature API libraries underneath:

```text
Anthropic SDK
OpenAI SDK
Google SDK
OpenRouter-compatible API
llama.cpp/vLLM endpoint
```

Cortex worker owns:

```text
message normalization
tool loop
retry semantics
timeout
context budget
usage accounting
checkpoint
event emission
```

This could realistically remain a relatively small codebase.

Small enough that Luke understands essentially every important line.

That's worth a lot.

---

# I'd optimize for **boring**

The ideal Cortex production log should be boring.

```text
12:00 task leased
12:00 workspace created
12:01 worker started
12:04 checkpoint
12:07 tests passed
12:08 verifier passed
12:08 task complete
```

Not:

```text
NEW MULTIAGENT MEMORY ARCHITECTURE 🎉
```

followed by four days fixing integrations.

You don't need framework innovation anymore.

**The innovation belongs in Cortex's orchestration.**

The worker should be plumbing.

---

# I'd establish an “Enterprise Stable” branch

Something like:

```text
main
develop
stable/1.x
```

But importantly:

### `stable/1.x` does not track main.

Promotion is one-way:

```text
develop
   ↓
soak test
   ↓
candidate
   ↓
30-day fleet testing
   ↓
stable
```

Stable gets:

* critical security fixes
* data-loss fixes
* severe provider compatibility fixes

That's it.

No features.

---

# And dependencies need freezing too

A stable Pi commit isn't stable if this happens:

```text
npm install
↓
63 transitive dependencies changed
```

So lock everything.

Prefer:

```text
package-lock / pnpm lock
container digest
Node version
OS image digest
Python version
Docker image digest
```

not:

```text
node:latest
postgres:latest
```

Production Cortex should be reproducible to the byte where reasonably possible.

---

# I would also use long-lived base images

For example:

```text
Ubuntu LTS
Postgres supported major
Node LTS
Python supported minor
```

No rolling Linux distribution.

No “latest”.

You want to be able to rebuild a 2027 Cortex worker in 2029 and have it behave predictably.

---

# The other big stability principle: **immutable workers**

Don't SSH into a worker and fix it.

Don't let an autonomous agent update its own runtime.

This is particularly important.

Worker image:

```text
cortex-worker-pi:1.4.2
```

is immutable.

An agent discovers a bug?

It files:

```text
runtime_issue
```

Cortex engineering builds:

```text
1.4.3
```

Tests it.

Canaries it.

Promotes it.

The running AI cannot mutate its own foundation.

That alone will eliminate an entire class of “self-improving system accidentally destroyed itself” failures.

---

# I'd even separate “stable” and “experimental” fleets

This gives you both worlds.

```text
                 CORTEX
                   │
        ┌──────────┴──────────┐
        │                     │
   STABLE FLEET         LAB FLEET
        │                     │
 Pi frozen 0.84         Pi newest
 Claude pinned          Qwen newest
 known models           new models
 strict policy          experimental
```

Then the lab can be adventurous.

Production never cares.

If something proves meaningfully better:

```text
Lab
 ↓
benchmark
 ↓
chaos
 ↓
soak
 ↓
canary
 ↓
Stable
```

No surprises.

---

# Here's where I've landed

Your requirements make me less enthusiastic about **Pi itself**, but *more* enthusiastic about **Pi's design philosophy**.

The winning principles are:

**small**

**stateless-ish**

**replaceable**

**model-agnostic**

**tool-driven**

**easy to supervise**

But you don't necessarily need to inherit Pi's release lifecycle to get those advantages.

### So my preference now is:

**1. Cortex-owned tiny worker/runtime**

**2. Frozen/vendorized Pi worker as the first sophisticated implementation**

**3. Claude Code adapter as premium specialist**

**4. OpenHands adapter only where its sandbox/workspace functionality clearly wins**

**5. Hermes adapter maintained for compatibility**

And I'd make the Cortex Core's defining promise:

> **A stable Cortex installation never requires upgrading its coding-agent runtime merely because upstream released something new.**

That's the architecture that directly solves the pain you're describing rather than moving the same problem from **Hermes → Pi**.

[1]: https://github.com/agentic-labs/pi-mono/blob/main/AGENTS.md?utm_source=chatgpt.com "pi-mono/AGENTS.md at main · agentic-labs/pi-mono · GitHub"
[2]: https://github.com/OpenHands/docs/issues/657?utm_source=chatgpt.com "❓ Agent Canvas transition FAQ · Issue #657 · OpenHands/docs · GitHub"
[3]: https://github.com/OpenHands/enterprise/issues?utm_source=chatgpt.com "Issues · OpenHands/enterprise · GitHub"
[4]: https://github.com/OpenHands/OpenHands/issues/13475?utm_source=chatgpt.com "V1 self-hosted: repository is cloned into a subdirectory while setup and hook logic assume repo root at workspace root · Issue #13475 · OpenHands/OpenHands · GitHub"
