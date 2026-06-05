# Offline Knowledge Stack — Scenario Guide

Hermes Cortex's offline capabilities enable two distinct scenarios. This guide documents
both and explains how to prepare for each.

---

## Scenario 1: Jungle Travel (Medical + Cultural + Language)

**Who:** Travellers going to remote areas with no internet.

**Goal:** Have a complete offline queryable knowledge base for health emergencies,
cultural navigation, language help, and geography.

### Pre-Flight Checklist

```bash
# 1. Download the travel bundle (~6 GB)
hermes-cortex/offline/prep-offline.sh --mode=travel

# 2. Verify everything is loaded
offline_knowledge stats
# Expected:
#   ✅ Web Cache — ready
#   ✅ kiwix-serve — running (localhost:8080)
#   📚 ZIM Content: 4 files, ~6 GB total
#       🌍 Wikivoyage (text-only, 232 MB)
#       🏥 WikiMed (2.1 GB)
#       🔤 Simple Wikipedia (3.4 GB)
#       📝 Wiktionary (2.2 GB)

# 3. Seed cache with survival-specific queries
python3 ~/.hermes/web-cache/web_cache.py pre-seed \
  --topics="jungle survival, tropical diseases, snake bites, water purification, \
            edible plants, first aid, local customs, language phrases"
```

### Daily Usage

| Need | Ask Moses | Source |
|---|---|---|
| **Medical emergency** | `"What are the symptoms of dengue fever?"` | WikiMed |
| **First aid** | `"How do I treat a deep cut in the jungle?"` | WikiMed |
| **Local culture** | `"What are the customs of the Dayak people?"` | Simple Wikipedia |
| **Language help** | `"How do I say 'thank you' in Indonesian?"` | Wikivoyage phrasebooks |
| **Geography** | `"What's the elevation and climate of this region?"` | Simple Wikipedia / Wikivoyage |
| **Navigation** | `"What towns are within a day's walk?"` | Wikivoyage |
| **Plants & animals** | `"Is this mushroom safe to eat?"` | Simple Wikipedia |
| **Women's health** | (Hesperian PDFs loaded into gbrain) | gbrain RAG |

### Sample Sessions

```
You: "Moses, my wife has a fever, headache, and joint pain. What should we do?"

Moses →
  [Cascade: cache miss → kiwix/WikiMed hit]
  
  WikiMed says: These symptoms match **dengue fever**.
  
  Key facts for this region:
  • Dengue is transmitted by daytime mosquitoes
  • Incubation: 4-10 days after bite
  • Symptoms: high fever, severe headache, joint/muscle pain, rash
  • Treatment: rest, hydration, acetaminophen (NOT ibuprofen/aspirin — bleeding risk)
  • Danger signs (seek evacuation): severe abdominal pain, persistent vomiting,
    bleeding gums, difficulty breathing
  
  There is a clinic in [nearest town] — the Wikivoyage guide lists it as 3 hours
  by boat. I recommend going if danger signs appear.
```

```
Your wife: "Moses, what local plants can I use for an antiseptic?"

Moses →
  [Cascade: cache miss → kiwix/Simple Wikipedia hit]
  
  Based on the region's flora, these plants have antiseptic properties:
  1. Tea tree oil (Melaleuca) — if you brought it
  2. Aloe vera — common in tropical areas, sap soothes and disinfects minor wounds
  3. Coconut oil — contains lauric acid, mild antimicrobial
  4. Turmeric — if available, paste on wounds (traditional use, some evidence)
  
  ⚠️ Avoid unknown plants. Many toxic lookalikes exist.
  
  Always clean wounds with boiled (then cooled) water first.
```

---

## Scenario 2: No-Internet Development (Build + Code + Docs)

**Who:** Developers coding offline for extended periods.

**Goal:** Full offline dev environment with docs, package cache, and knowledge
reference.

### Pre-Flight Checklist

```bash
# 1. Download the build bundle (~7 GB)
hermes-cortex/offline/prep-offline.sh --mode=build

# 2. Cache pip wheels for your projects
pip download -r your-project/requirements.txt -d ~/offline/pip-cache/
# Or for all commonly used packages:
pip download --dest ~/offline/pip-cache/ \
  flask fastapi requests sqlalchemy pytest black mypy numpy pandas

# 3. Clone working repos (full history)
git clone --depth=10000 https://github.com/your/project ~/offline/repos/project

# 4. Seed cache with dev-specific queries
python3 ~/.hermes/web-cache/web_cache.py pre-seed \
  --topics="python async patterns, sqlite optimization, Docker networking, \
            macOS development, JavaScript async, CSS grid, git workflows"
```

### Offline Install Pattern

```bash
# When you need a new package offline:
pip install --no-index --find-links ~/offline/pip-cache/ flask

# If the package isn't cached:
# Moses can help find an alternative or work around it
```

---

## Scenario 3: Kid Learning (Education)

**Who:** Children learning during long offline periods.

**Goal:** Engaging educational content with Moses as an interactive tutor.

### Pre-Flight Checklist

```bash
hermes-cortex/offline/prep-offline.sh --mode=education
# Downloads: Simple Wikipedia (3.4 GB) + Wikibooks (1.5 GB) + Wikivoyage (232 MB)
```

### Daily Usage

| Kid asks | Moses does | Source |
|---|---|---|
| `"Why is the sky blue?"` | Explains Rayleigh scattering | Simple Wikipedia |
| `"How do I multiply fractions?"` | Finds lesson, gives examples | Wikibooks |
| `"Tell me about dinosaurs"` | Synthesizes article | Simple Wikipedia |
| `"What's the capital of France?"` | Quick lookup | Simple Wikipedia |
| `"Teach me about electricity"` | Finds Wikibooks chapter, quizzes | Wikibooks |

### Tutor Mode

```
Kid: "Why do volcanoes erupt?"

Moses →
  [Cascade: Simple Wikipedia → Wikibooks]
  
  Great question! Let me explain in simple terms:
  
  **What's inside the Earth?**
  Deep underground, it's so hot that rock melts into liquid called **magma**.
  Think of it like a bottle of soda that's been shaken up.
  
  **How does it erupt?**
  1. Magma has gases dissolved in it (like CO₂ in soda)
  2. The gases build up pressure
  3. When there's a crack in the Earth's crust, the pressure pushes
     the magma up and out — just like opening that shaken soda bottle!
  
  **Fun fact:** There are about 1,500 active volcanoes on Earth. Most are
  underwater!
  
  Want to learn about the different types of volcanoes? Or try a quiz?
```

---

## Architecture: How It All Fits Together

```
┌──────────────────────────────────────────────────────────────────┐
│                      AGENT (Moses)                               │
│  Receives question → runs cascade → synthesizes answer           │
└──────────┬───────────────────────────────────────┬────────────────┘
           │                                       │
    ┌──────▼──────┐                         ┌─────▼──────┐
    │  Online Mode │                         │ Offline    │
    │  (internet)  │                         │ Mode       │
    └──────┬───────┘                         │ (no net)   │
           │                                 └─────┬──────┘
    ┌──────▼───────────────────┐          ┌─────────▼──────────┐
    │  1. web_cache (fastest)  │          │  1. web_cache       │
    │  2. kiwix ZIM (free)     │          │  2. kiwix ZIM       │
    │  3. web_search (API $)   │          │  3. gbrain (RAG)    │
    │  4. LLM native           │          │  4. LLM native      │
    └──────────────────────────┘          └────────────────────┘
```

## Migrating Between Machines

The entire offline setup is portable:

```bash
# On source machine:
cp -r ~/offline /Volumes/USB/offline-backup

# On target machine:
cp -r /Volumes/USB/offline-backup ~/offline
hermes-cortex/offline/prep-offline.sh  # re-runs setup (skips downloads if files exist)
```

## Resource Budget (for the jungle laptop)

| Component | RAM | Disk | Notes |
|---|---|---|---|
| macOS | ~2 GB | — | Base OS |
| Docker (kiwix-serve) | ~500 MB | ~6 GB (ZIM) | Lightweight container |
| Ollama (Qwen3:4b) | ~2.5 GB | ~2.8 GB | Chat model |
| Ollama (nomic-embed-text) | ~300 MB | ~300 MB | Embeddings (shared) |
| **Total** | **~5.3 GB** | **~9 GB** | Leaves room for browser/docs |

On an 8 GB machine: ~2.7 GB free for apps.
On a 16 GB machine: ~10.7 GB free — comfortable.
