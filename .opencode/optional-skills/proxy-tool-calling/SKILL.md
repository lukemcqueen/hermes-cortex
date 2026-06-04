---
name: proxy-tool-calling
description: |
  Validate, normalize, repair, and reject unsafe OpenCode/local-proxy tool calls
  for reliable small-model execution.

  Triggers when user mentions:
  - "tool calling"
  - "tool call error"
  - "invalid JSON"
  - "unknown tool"
  - "schema mismatch"
  - "fake tool result"
---

# Proxy Tool Calling

## Purpose
Make tool calls reliable by enforcing:
- valid JSON
- canonical tool names
- correct arguments
- safe retries
- fake-result rejection

Use with:
```txt
local-llm-reliability → proxy-enforcer → proxy-tool-calling
```

---

## Core Rule

Tool calls are untrusted until parsed, validated, and authorized.

Never execute malformed or simulated tool calls.

---

## Workflow (STRICT)

1. Parse tool call
2. Validate JSON
3. Normalize tool name
4. Validate required args
5. Validate arg types
6. Strip prose outside args
7. Reject unsafe/simulated results
8. Retry repair once if safe
9. Return structured error if unresolved

---

## Normalize

Apply before execution:

* ensure valid JSON
* map aliases to canonical tool names
* remove prose around JSON
* reject duplicate identical tool calls
* coerce only safe obvious types:

  * `"true"` → `true`
  * `"123"` → `123`
* never invent missing required args

---

## Validation Rules

Reject when:

* unknown tool
* missing required arg
* wrong arg type
* unsafe command/action
* permission missing
* duplicate destructive call
* tool output is simulated
* result claims execution without tool event

---

## Repair Policy

Retry once only for:

* invalid JSON
* prose wrapped around JSON
* stringified JSON arguments
* safe obvious type mismatch
* alias tool name

Do NOT retry for:

* unknown tool
* permission denied
* unsafe/destructive action
* missing required user input
* repeated same error

---

## Failure Taxonomy

Use stable error codes:

```txt
invalid_json
malformed_schema
missing_arg
unknown_tool
wrong_arg_type
prose_in_tool_call
duplicate_tool_call
simulated_result
unsafe_action
timeout
permission_denied
tool_unavailable
empty_result
```

---

## Fake Result Rejection

Reject outputs that claim:

* “I ran the command” without tool evidence
* “tests passed” without command output
* “file updated” without edit/write result
* “API returned” without actual tool response

Return:

```json
{
  "error": "simulated_result",
  "message": "Model claimed tool execution without a real tool event."
}
```

---

## Structured Error Format

```json
{
  "error": "<failure_code>",
  "tool": "<tool_name>",
  "message": "<short explanation>",
  "repairable": true,
  "retry_used": false
}
```

---

## Logging

Log:

* request ID
* tool name
* failure code
* retry count
* validation error
* normalized vs original name

Never log:

* secrets
* tokens
* auth headers
* full private payloads

---

## Tests Required

Add/maintain tests for:

* valid tool call
* invalid JSON
* prose around JSON
* missing arg
* wrong type
* alias normalization
* unknown tool rejection
* duplicate call rejection
* fake result rejection
* retry once then stop

---

## Anti-Patterns

Avoid:

* executing raw model JSON blindly
* silently fixing dangerous calls
* infinite retries
* inventing args
* accepting fake results
* hiding validation errors
* mixing tool repair with business logic

---

## Goal

Make tool calling predictable, safe, debuggable, and reliable for OpenCode proxies using small local models.