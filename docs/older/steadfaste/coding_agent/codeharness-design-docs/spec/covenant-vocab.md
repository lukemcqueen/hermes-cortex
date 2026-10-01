# The Covenant Vocabulary — what we call things, and why

> **The principle:** a business owner with no tech expertise should understand,
> at least conceptually, what each component is and how the components interact —
> **from the names alone.** Every word either carries the meaning or is kept
> because it's already clear and universal. We rename only where the old word
> was bland or jargony and a covenant-toned word genuinely helps. **We do not
> rename for the sake of it** — coherence and intelligibility are the goal, so
> whatever already works is maintained as-is.
>
> **Reader:** a *business owner* should be able to read the one-line story below
> and know the whole product conceptually without touching technical docs.

## The one-line story

> You give the **Agent** a **Mandate** (a single job's orders). The **Constitution**
> — the dependable core — is the supreme law the whole system runs inside: it
> enforces that Mandate within the **Charter** (the rules you set: what it may
> spend, touch, and approve) and cannot be overruled or rewritten by the Agents
> and Workers it governs. When the Agent is unsure it **seeks guidance**, and a
> human **Steward** **ratifies** or **vetoes**. Every step is recorded in the
> **Ledger**. It all holds together by the **Covenant** — the bond of trust —
> and we still verify everything before we trust it.

## Constitution vs Covenant — the core and the bond

**They pair, they don't conflict:**

| | **Covenant** | **Constitution** |
|---|--------------|------------------|
| What it is | the **bond of trust** — the promise, the spirit, the agreement between the core and every Agent/Steward | the **supreme written law** — the letter, the binding rules the whole system runs inside |
| Feels like | an agreement made in good faith | the unamendable law everything lives under |
| Cannot be | broken lightly (a breach is serious) | overruled or rewritten by the Agents/Workers it governs |

**In one breath:** the **Covenant** is the trust we build the system on; the
**Constitution** is that trust written as law — the dependable core that cannot
be touched from inside. "Trust is the core of the core": the Covenant is the
trust, the Constitution is the core that holds it.

## What we renamed (the covenant words)

| Old | New | What it is | Why the covenant word |
|-----|-----|-----------|----------------------|
| the core / Boss | **Constitution** | the dependable core | the supreme law — unamendable and unoverrulable from inside; trust written as law |
| Governor (policy) | **Charter** | the rules a business edits | a charter grants power *and* limits, like a constitution for a single scope |
| policy | **Mandate** | one job's specific orders | a mandate = binding instruction within limits |
| human / HITL | **Steward** | the person who cares for + is answerable for the system | a steward is accountable for what it does not own — it ratifies, vetoes, and owns the residual risk on behalf of the enterprise |
| record / journal | **Ledger** | the unchangeable audit | a ledger is append-only and trustworthy |
| intent journal | **Ledger of intent** | what was *about* to happen | extends the same trustworthy record |
| `start` | `commission` | grant the Agent the task | you *commission* work |
| `redirect` | `direct` | a Steward's new course | a human direct-rule |
| `human_decided` | `ratified` | a Steward approved | formally stood behind it |
| `deny` | `veto` | block a capability | stronger, weightier |
| `needs_human` | `seeks_guidance` | Agent asks a human | trust-based asking |
| `VERIFIED_BY_HUMAN` | `RATIFIED` | a state | the Steward stood behind it |
| `UNVERIFIED` | `UNENDORSED` | a state | we haven't stood behind it |
| `NO_ORACLE` | `UNDECIDABLE` | a state | honestly unprovable |

## Agent vs Worker — a layered, both-swappable distinction

**These are two layers, and BOTH may be swapped.** The Constitution (steadfaste's
core) + Covenant govern whatever comes and goes beneath it.

| | **Worker** | **Agent** |
|---|-----------|-----------|
| What it is | the **clinical, replaceable motor** — the out-of-process mechanical engine (Claude, Pi, our own) | the **governed acting entity** — a Worker wrapped in the Charter + Mandate + Covenant |
| Authority | **low** — it is a tool; disposable, pinned | **delegated but bounded** — acts *on your behalf*, seeks guidance, gets ratified/vetoed |
| Swap-ability | **swappable** — you pick the motor freely | **also swappable** — you can swap a whole Agent (a different governed wrapper/harness's agent) and steadfaste still governs it |
| Who stays | the **Constitution + Covenant** — the governance — is steadfaste's and stays | the Constitution governs whatever Agent/Worker comes and goes |

**Plain words:** the Worker is the motor; the Agent is that motor *given
responsibility* (wrapped in Charter/Mandate, watched by a Steward, bound by the
Covenant). Both are pluggable — a third party can plug in a **Worker** OR a
whole **Agent**. What makes it steadfaste is not the Agent or Worker; it is the
**Constitution + Covenant** that governs them. That is why "the core + its
interfaces" is the one thing we do well: it governs any Agent/Worker built around
it.

## What we KEEP as-is (already clear & universal — maintained for coherence)

These stay. They're understood by everyone and renaming them would *hurt* clarity:

**Players/things:** Agent · Model · Brain · Job · Task · Budget · Permission ·
Approval · Audit · Post-mortem · Lesson · Template · Verification · Conformance ·
Capability.

**Verbs/states:** `started` · `progress` · `result` · `failed` · `stopped` ·
`cancel` · `stop` · `trusted|untrusted` · `VERIFIED_BY_GATE` ·
`REJECTED_UNTRUSTED`.

**Mechanics:** Retry · Timeout · Cost · Contract (the wire format) · Frame ·
Handshake · Deny-list.

## Two deliberate distinctions (kept in the language)

| Word | Reserved for | Not for |
|------|--------------|---------|
| `failed` | a routine task failure — expected, retried, healed | NOT a big dramatic event |
| `breached` | a **trust** violation (protective layer: a model/plugin/actor violated the covenant) | NOT a normal failed test → so we don't over-dramatize day-to-day |

Keeping `failed` for routine failure and reserving `breached` for a *trust*
break keeps the language honest: a failed test is normal and healed; a *breach*
is serious and human-escalated.

## Rule going forward

When a new concept gets a name:
1. Is it already clear and universal (Agent, Budget, Audit)? → keep it.
2. Does it need a covenant-toned word to carry meaning (the core, the human,
   the rules)? → constitution-charter-mandate-steward-ledger family.
3. Never rename what working — coherence and intelligibility win over novelty.

That is how "trust is the core of the core" stays real in the language without
renaming everything into poetry.