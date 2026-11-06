# Skill-Drift Gate — skill_manage writes deployed only, repo lags (2026-08-27)

## Symptom

After patching a repo-managed skill via `skill_manage`, the next
`fleet-update.sh` run prints:

```
⚠   SKILL DRIFT: devops/<skill> — deployed copy is newer than repo source!
⚠     → Repo: $HOME/steadfaste-fleet/skills/devops/<skill>/SKILL.md
⚠     → Deployed: $HOME/.steadfaste-fleet/skills/devops/<skill>/SKILL.md
⚠     → Copy the deployed changes to the repo source, then fleet-update.sh will sync.
```

## Root cause

`skill_manage` patches write to the DEPLOYED copy
(`~/.steadfaste-fleet/skills/<cat>/<name>/SKILL.md`). The repo source
(`~/steadfaste-fleet/skills/...`) is the fleet truth and does NOT move —
so the lesson never reaches the fleet, and the next push can fail the
Deploy-sync gate ("deployed != repo").

## Fix

```bash
cd ~/steadfaste-fleet
cp ~/.steadfaste-fleet/skills/devops/<skill>/SKILL.md skills/devops/<skill>/SKILL.md
git add skills/devops/<skill>/SKILL.md
git commit -m "docs(skills): sync deployed lessons to repo source"
# then dogfood (deploy) before push:
bash ~/.steadfaste-fleet/scripts/fleet-dogfood.sh --force
git push origin main
```

## When this bit us

2026-08-27: patched `deploy-load-verification` and `shared-repo-push-gates`
mid-session with the mem-plugin registration-order lesson and the
PENDING-cycle/deploy-sync gate lessons. The AGENTS.md prune commit's
fleet-update run surfaced the drift; both skills were cp'd back and pushed
in `5258cceb`.

## Habit

After ANY `skill_manage` patch/edit in the steadfaste-fleet repo: `cp` the
deployed SKILL.md back to the repo source and commit in the same cycle.
Treat "deployed copy is newer than repo source" as a blocker-equivalent
warning — it means your lesson is orphaned from the fleet.
