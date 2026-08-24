---
name: role-gating-and-public-moderation
description: Role gating, PII tiers, and UGC moderation patterns.
version: 1.0.0
category: software-development
platforms: [linux, macos]
---

# Role Gating & Public-Content Moderation

Patterns for a multi-role product with an anonymous/public surface plus
privileged surfaces (admin/editor) and user-submitted public content
(directory/listings/reviews). Distilled from the Example church-directory +
prayer-warrior build; see `references/fastapi-example.md` for the concrete
FastAPI implementation.

## 1. Public registration must NEVER grant a privileged role
- The public `{register}` endpoint must **force `role = seeker`** and ignore any
  client-supplied role. Drop the `role` field from the request schema entirely
  so a malicious payload is silently dropped by the validator.
- Privileged roles (admin/evangelist/approved-warrior) come ONLY from a
  sanctioned bootstrap path (seed script, admin approval, owner action) —
  never from the public endpoint.
- Write a **RED test** proving escalation is dead: `register({role:"admin"})` →
  login → `/auth/me` returns `role == seeker`, and that account is **403** on
  every privileged surface.

## 2. Approval-gated role bootstrap (self-serve signup that needs a review)
- For roles where "anyone may apply but few should be admitted" (e.g. prayer
  warriors vs. unrestricted seeker signup): the public signup creates a REAL
  account in a **pending** state with `role` still `seeker` — NO privileged
  access until an owner approves.
- Add a status column (e.g. `warrior_status` pending | approved). The role is
  promoted only on approval (role → `warrior`, status → `approved`).
- Owner/approval endpoint is admin-gated and idempotent.

## 3. Rework test fixtures through the sanctioned path, not the old exploit
- When you close a privilege hole, existing tests that created privileged
  accounts *through the vulnerable endpoint* will break. Do NOT re-open the
  hole for them — update the fixtures to bootstrap via the seed/sanctioned
  helper (e.g. `ensure_user(session, email, pw, role, force_role=True)` +
  commit), then login normally. The same helper powers the seed script.

## 4. PII-tiered read model (owners vs peers)
- When peers can see one another, expose a **non-PII only** serialization
  (id, pseudonym/nickname, country) on the peer/community endpoint — never
  email, password, verification flags, or role.
- Owners (admin) see **full PII** via a separate admin endpoint.
- Own-profile endpoint may return the caller's own full PII.
- Add a test that asserts the protected keys are absent from the public/peer
  payload (e.g. `forbidden not in entry` for email/status/flags).

## 5. UGC moderation lifecycle (submit → review → approve)
- Public submissions create entries with `status = pending`, **hidden** from the
  public. Only `status == approved` appears publicly.
- State machine: `pending → approved | rejected | needs_info`. Owner review
  endpoint sets status + review notes + an optional harm/abuse flag.
- **Blocklist filter**: screen submissions against a curated, editable
  blocklist (name/denomination match) → auto-`rejected` + flagged. Flagged
  entries are NEVER public, even if later approved by mistake.
- **Editor-trusted path**: staff/editor-created entries can go straight to
  `approved`/public; only anonymous submissions enter the review queue.
- **Responsible pairing**: do NOT make filtering purely punitive. Pair the
  blocklist with a public "awareness / help" resources page (editable notice +
  an anonymous self-check that is never stored), and have flagged submissions
  return a `help_url` so submitters are offered help, not just rejection.

## 6. Pitfall — appending a FastAPI dependency can strip the prior function's return
When adding a second dependency function next to an existing one (e.g. add
`get_current_admin` below `get_current_evangelist`), a replace-style patch can
accidentally consume the first function's trailing `return user`, so it falls
through and returns `None` — turning every gated endpoint into a 500. After any
such edit, confirm the ORIGINAL function still ends in `return user` (or run
the suite; the data-domain tests will catch it as 500s while auth tests pass).

## Verification
Run the full API test suite (auth + RBAC + moderation) and assert:
- register-with-privileged-role → seeker + 403s
- peer community endpoint leaks no PII keys
- public browse shows only approved + non-blocklisted
- approval/denial lifecycle moves entries in/out of public visibility
