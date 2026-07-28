After these 10:
- Select reasoning pattern
- Classify with agent-flow
- Load on-task skills
- Run cronjob list + search_files
- **Write the skills-loaded marker: `touch ~/.hermes-cortex/state/.skills-loaded`**
- **THEN** call `begin_change`

## Enforcement

The governance enforcer plugin now blocks ALL write tools (patch, write_file,
terminal with write commands, cronjob, skill_manage, process) unless
`~/.hermes-cortex/state/.skills-loaded` exists. You cannot write anything
without first loading the 10 always skills.

After `end_change()`, the marker is automatically removed so the next task
requires fresh loading. No bypass flags exist for this check.

## Self-Verification