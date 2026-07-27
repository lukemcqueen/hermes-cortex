# Loop Governance Config Format

## File location

`~/.hermes/data/loop-governance-config.json`

## Schema

```json
{
  "version": 1,
  "weights": {
    "completeness": 0.40,
    "quality": 0.30,
    "progress": 0.30
  },
  "thresholds": {
    "stop": 8.0,
    "loop": 5.0,
    "move_on": 3.0,
    "no_progress_score": 2.0,
    "no_progress_limit": 3
  },
  "auto_apply": {
    "min_confidence": 0.7,
    "max_threshold_delta": 1.0,
    "max_weight_delta": 0.10,
    "requires_review": true
  }
}
```

## Field descriptions

### weights

Controls how each scoring dimension contributes to the composite score. Must sum to 1.0.

| Field | Default | Range | Description |
|-------|---------|-------|-------------|
| `completeness` | 0.40 | 0.05–0.80 | Weight for goal-achievement score |
| `quality` | 0.30 | 0.05–0.80 | Weight for code quality score |
| `progress` | 0.30 | 0.05–0.80 | Weight for iteration-over-iteration change |

### thresholds

Defines the decision boundaries for the STOP/LOOP/MOVE ON matrix.

| Field | Default | Range | Description |
|-------|---------|-------|-------------|
| `stop` | 8.0 | 5.0–10.0 | Composite ≥ this → STOP ✓ |
| `loop` | 5.0 | 1.0–9.0 | Composite between loop and stop → LOOP 🔄 |
| `move_on` | 3.0 | 1.0–5.0 | Composite between move_on and loop → MOVE ON → |
| `no_progress_score` | 2.0 | 0.0–5.0 | Progress < this → no-progress flagged |
| `no_progress_limit` | 3 | 1–5 | Consecutive no-progress → HARD FAIL |

### auto_apply

Safety bounds for automatic config changes from the weekly evaluation.

| Field | Default | Range | Description |
|-------|---------|-------|-------------|
| `min_confidence` | 0.7 | 0.5–0.95 | Skip patches below this confidence |
| `max_threshold_delta` | 1.0 | 0.1–2.0 | Max per-threshold change per apply |
| `max_weight_delta` | 0.10 | 0.02–0.20 | Max per-weight change per apply |
| `requires_review` | true | bool | When true, high-confidence patches still wait for human review |

## Viewing and editing

```bash
# View current config
loop-config

# View as JSON
python3 ~/.hermes-cortex/tools/loop-governance/loop_config.py --show

# Set a value
python3 ~/.hermes-cortex/tools/loop-governance/loop_config.py --set weights.completeness 0.45

# Or edit directly
vim ~/.hermes/data/loop-governance-config.json
```

## Rollback

The `config_history` table in the loop-governance DB stores every change. To roll back:

```python
from loop_db import LoopDB
from loop_config import update_config

db = LoopDB()
# Find the config before the bad change
rows = db.conn.execute(
    "SELECT * FROM config_history ORDER BY id DESC LIMIT 5"
).fetchall()
# rows[0] is most recent — restore rows[1]'s config
import json
previous = json.loads(rows[1]["config_json"])
update_config(previous)
db.close()
```