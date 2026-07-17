--- Full content (truncated) ---
---
name: telephony
description: Give Hermes phone capabilities without core tool changes. Provision and persist a Twilio number, send and receive SMS/MMS, make direct calls, and place AI-driven outbound calls through Bland.ai or Vapi.
version: 1.0.0
author: Nous Research
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [telephony, phone, sms, mms, voice, twilio, bland.ai, vapi, calling, texting]
    related_skills: [maps, google-workspace, agentmail]
    category: productivity
---

# Telephony — Numbers, Calls, and Texts without Core Tool Changes

This optional skill gives Hermes practical phone capabilities while keeping telephony out of the core tool list.

It ships with a helper script, `scripts/telephony.py`, that can:
- save provider credentials into `~/.hermes/.env`
- search for and buy a Twilio phone number
- remember that owned number for later sessions
- send SMS / MMS from the owned number
- poll inbound SMS for that number with no webhook server
... [truncated]
--- End skill ---