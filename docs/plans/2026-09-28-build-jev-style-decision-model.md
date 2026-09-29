# Building a Jev-style (System One) Decision Model from the Ground Up

**Date:** 2026-09-28 · **Author:** Moses (for Luke) · **Status:** Research / decision input
**Target corrected:** Jev is a **System One decision model** from TypeSafe AI — NOT an LLM,
NOT Devin. This document is the research basis for building something with some of Jev's
functionality ourselves.

## What Jev actually is (the correct target)
- **Type:** a decision model, not a text generator. It takes unstructured *state* + typed
  *questions*, and returns **structured typed values**, not strings.
- **Three primitives (question types):**
  - **Choice** — pick one of K described options → selected option + per-option probabilities + confidence
  - **Score** — rate state on an ordered rubric → score + per-level probabilities + confidence
  - **Noul** — evaluate a yes/no statement → probability in [0,1]
- **Non-autoregressive:** all answers emitted in **one parallel forward pass** (no token-by-token
  decoding). This is where the 40–200× speed advantage comes from.
- **No hallucination, no type errors by construction** — output space is fixed in advance by the schema.
- **Calibrated:** higher probability ⇒ higher accuracy. "Model can do it 95% of the time and
  tells you when it's in the 5%."
- **Trained with RLCD** (Reinforcement Learning for Calibrated Decisions) — optimizes
  probabilities against **outcomes**, not human preference (vs RLHF) and not verifiable-text
  rewards (vs RLVR).
- **Trained on synthetic data only.** Transformer-based. Exact architecture/weights unpublished
  (proprietary). Price $0.042/MTok input, output free, 70–500 ms.

## The key realization: this is FAR more tractable than an LLM
You told me "smaller specialized models" — and Jev itself is not an LLM at all. A decision
model is essentially a **calibrated scoring model**: encode the state, score each declared
option/level, softmax → probabilities. Since there's no language generation, there's no
tokenizer-training, no autoregressive decode, no massive pretraining corpus demand. That means
**you can build a genuinely useful Jev-like model on laptop-grade compute.**

Equally important: **the open-source field already reproduced the architecture** (within ~24h
of Jev's launch). You don't have to invent anything — you can start from a proven blueprint.

## The canonical open architecture (von — the best reference)
**Von** (wfzyx/von, Apache-2.0) is a complete non-autoregressive System One decision
model: a **395M ModernBERT (large) encoder** + **option-marker head**. One forward pass scores
all declared options against the state; softmax over options gives the distribution. CPU-served
(OpenVINO), also CUDA/ROCm/MPS. Wire-compatible with TypeSafe's `/v1/systemone` spec.

Its `training/` directory is literally the open recipe you want. It contains:
- **Synthetic data generators** (`generate_synthetic_decisions.py`, `generate_standard_spines.py`,
  `generate_numeric_decisions.py`, `generate_adequacy_decisions.py`, `prepare_universal_dataset.py`)
- **`train_option_marker.py`** — trains the option-marker head (choice/score/noul)
- **`train_rlcd.py`** — implements the RLCD method directly (4-GPU DDP)
- **Distillation** (`prepare_distill_dataset.py`, soft-label training)
- **Data hygiene** (`contamination_audit.py`, `balance_corpus.py`, `harden_corpus.py`)
- **AWS spot launcher** (`launch_aws_spot.py`) — cheap cloud training orchestration

## The ecosystem landscape (what to start from)
| Project | Params | Base | Train yourself? | Best for |
|---------|--------|------|-----------------|----------|
| **Von** | 395M | ModernBERT-large | Yes (full recipe) | **The ground-truth reference; leads open field** |
| **Laya** | 421M | ModernBERT-large + marker | Fine-tune | CPU-friendly, 100+ langs, pip install |
| **Kev** | 0.8/4/9B + LoRA | Qwen3.5 | Adapters | Drop-in for hosted Jev (same wire API) |
| **SemIf** | frozen Qwen3.5-4B | — | None (read logits) | Reuse a model you already host |
| **NanoJev** | 0.6B | Qwen3 + heads | Trained on 4 games | Real-time control loops (beats Jev on ViZDoom) |
| **jevlike** | any | byte encoder / any HF encoder | **Yes — laptop trainer** | **Your own label set, from scratch** |

**The honest calibration caveat** (from the independent 49-task jabr benchmark):
- Jev 0.966 macro accuracy vs best open (Von) 0.704 **zero-shot / out-of-domain** — a 26-pt gap.
- **In-domain, after you fine-tune on your own labels, the open models are competitive.**
- The gap is a *research* problem (training data / calibration), not an architecture problem.

## How to build it ourselves — recommended path
The **from-the-ground-up** route that actually works (they all start from a pretrained encoder;
TRUE from-scratch pretraining is only worth it for a novel architecture — `jevlike`'s byte-encoder
variant shows even a from-scratch tokenizer is optional):

1. **Pick the backbone:** ModernBERT-large (395M) is the proven choice — CPU-servable, good
   calibration. Use the base encoder, do NOT run it as a chat model.
2. **Define your decision schema:** your own Choice options, Score rubrics, and Noul questions.
3. **Synthesize training data:** generate synthetic decisions where the *correct answer is
   derivable* (extraction, routing, adequacy, numeric-ranking — copy `von`'s generator suite).
   This is where most of the effort goes — it's the "spine" of the model.
4. **Train the option-marker head** (fine-tune encoder + head): state+options → per-option
   scores → softmax. Copy `train_option_marker.py`.
5. **RLCD for calibration:** run `train_rlcd.py` to push probabilities to match outcomes
   (reliability), closing the confidence gap. This is the step LLM wrappers lack.
6. **Distill (optional, larger teacher → small student):** `prepare_distill_dataset.py`.
7. **Eval properly:** separable metrics — accuracy (top-1), **calibration error** (ECE/reliability
   diagram), + a shuffled-context control (option/context mismatch) that most projects skip.
8. **Serve:** one forward pass, CPU/OpenVINO, wire-compatible `/v1/systemone`; ~0.1s, free tier cost.

## Compute / cost reality
- **This host: NO GPU, 15 GB RAM.** A 395M encoder will fine-tune but slowly on CPU; for
  real iteration use a cheap cloud GPU (T4/RTX ~$0.5–1.5/hr, or `launch_aws_spot.py` + spot).
- **Budget anchors:** fine-tuning an open encoder + decision head on synthetic data is
  **$50–$300** for a small specialized model — not the $200–5k of LLM pretraining.
- The bottleneck is **data synthesis + calibration tuning**, not raw FLOPs.

## Decision point — three concrete options
1. **Laptop fine-tune, your own labels (fastest, ~zero cost):** use **jevlike** or fine-tune
   **Laya/von** on YOUR routing/taxonomy/decision labels on CPU/MPS. Proof in a day.
2. **Full open blueprint (~$100–300 cloud):** start from **von's** repo, synthesize your own
   decision corpus, train option-marker head + RLCD on a T4/L40S. This replicates Jev's *method*.
3. **Hybrid + on-host serving:** do (2), then deploy the 395M model on moses (CPU/OpenVINO) as
   a local `/v1/systemone` endpoint — a Jev-class decision service we own end-to-end, ~0.1s,
   free per call.

## Key risks / honest caveats
- **Zero-shot quality gap:** don't expect out-of-domain parity with Jev (0.704 vs 0.966 on the
  independent benchmark). Specialize for YOUR domain and it's competitive.
- **Calibration is the hard part** (reward hacking, overconfidence). RLCD + proper scoring-rule
  evals (Brier/log-loss/ECE) are mandatory, or the "confidence" is worthless for automation.
- **Data synthesis dominates effort.** Vanilla rewrite attempts produce near-chance models
  (Laya's base) — the synthetic corpus is the moat.
- Jev's weights are proprietary/unpublished; everything here is open-reimplementation-based.

## Counterpart: the `typesafe-ai` skill
Esther published **`typesafe-ai`** (skill, deployed to fleet 2026-09-29) covering *using* the
hosted Jev API — primitives, confidence semantics, composable judgment patterns, and a
`TYPESAFE_API_KEY` in `~/.hermes/.env`. That skill is about **consuming** Jev; this document
is about **building** a Jev-style model. They are complementary — use the skill if you want
the hosted API; use this document if you want to build/train our own.

## Immediate next step (needs your decision)
Reply **1, 2, or 3** (or "which domain" — e.g. what decisions you want it to make: routing,
scoring, guardrails, ticket triage) and I'll turn it into an executable plan: data-synthesis
generators → model card → training run → local `/v1/systemone` service on moses.
