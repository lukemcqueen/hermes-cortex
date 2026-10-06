# Skill-Drift Gate — skill_manage writes deployed only, repo lags (2026-08-27)

## Symptom

After patching a repo-managed skill via `skill_manage`, the next
`cortex-update.sh` run prints:

```
⚠   SKILL DRIFT: devops/<skill> — deployed copy is newer than repo source!
⚠     → Repo: $HOME/hermes-cortex/skills/devops/<skill>/SKILL.md
⚠     → Deployed: $HOME/.hermes-cortex/skills/devops/<skill>/SKILL.md
⚠     → Copy the deployed changes to the repo source, then cortex-update.sh will sync.
```

## Root cause

`skill_manage` patches write to the DEPLOYED copy
(`~/.hermes-cortex/skills/<cat>/<name>/SKILL.md`). The repo source
(`~/hermes-cortex/skills/...`) is the fleet truth and does NOT move —
so the lesson never reaches the fleet, and the next push can fail the
Deploy-sync gate ("deployed != repo").

## Fix

```bash
cd ~/hermes-cortex
cp ~/.hermes-cortex/skills/devops/<skill>/SKILL.md skills/devops/<skill>/SKILL.md
git add skills/devops/<skill>/SKILL.md
git commit -m "docs(skills): sync deployed lessons to repo source"
# then dogfood (deploy) before push:
bash ~/.hermes-cortex/scripts/cortex-dogfood.sh --force
git push origin main
```

## When this bit us

2026-08-27: patched `deploy-load-verification` and `shared-repo-push-gates`
mid-session with the mem-plugin registration-order lesson and the
PENDING-cycle/deploy-sync gate lessons. The AGENTS.md prune commit's
cortex-update run surfaced the drift; both skills were cp'd back and pushed
in `5258cceb`.

## Habit

After ANY `skill_manage` patch/edit in the hermes-cortex repo: `cp` the
deployed SKILL.md back to the repo source and commit in the same cycle.
Treat "deployed copy is newer than repo source" as a blocker-equivalent
warning — it means your lesson is orphaned from the fleet.
