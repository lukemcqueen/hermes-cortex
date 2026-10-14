# Observation — the running gate uses the narrowed pattern

This file is itself the observation. It intentionally contains the shape that
the OLD detector treated as a phone number: chained source-line references, e.g.
the Level 3 block at pre-commit-score:576-634 and the lock scan at
:5341-5377, with _check_lock at :5380-5401.

If the write of this file was ACCEPTED, the process serving the write gate is
running the narrowed pattern (the old one would have refused with
"phone number"). If it was REFUSED, the deployed code has not been loaded by
the running gateway and a restart is required.

Deploy ≠ load: `cortex-update.sh` puts the new module on disk, and a long-lived
gateway keeps the revision it started with. This file exists so the question is
settled by observation rather than by assuming a deploy implies a reload.

## The observation, as it happened

- BEFORE the deploy, in this same session and through this same gateway, a
  `patch` whose only offence was these chained line references was REFUSED with
  "🛑 PII GUARD — personal data in content being written … phone number". That
  refusal is the false positive this change fixes.
- AFTER `cortex-update.sh` + dogfood, the write of THIS file — containing the
  same shape — was ACCEPTED.

Same session, same process, opposite verdicts on the same content: that is the
reload observed rather than assumed. No restart was needed.
