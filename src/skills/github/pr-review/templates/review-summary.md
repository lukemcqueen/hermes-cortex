## Hermes PR Review — #{{ PR_NUMBER }}

**Verdict:** {{ VERDICT }}

**PR:** {{ PR_TITLE }} by {{ PR_AUTHOR }}

**Scope:** `+{{ ADDITIONS }} / -{{ DELETIONS }}` across **{{ FILE_COUNT }}** files
**Tests:** {{ TEST_STATUS }}
**Architecture:** {{ ARCH_STATUS }}
**Security:** {{ SEC_STATUS }}

---

### 🔴 Critical ({{ CRIT_COUNT }})

{{ CRITICAL_ITEMS }}

### ⚠️ Warnings ({{ WARN_COUNT }})

{{ WARN_ITEMS }}

### 💡 Suggestions ({{ SUGGEST_COUNT }})

{{ SUGGEST_ITEMS }}

### ✅ What's Good

{{ GOOD_ITEMS }}

---

*Reviewed by Hermes Agent | Architecture: deep-module ✓ | Security: static scan ✓ | Lessons: {{ LESSON_MATCHES }} matches*
