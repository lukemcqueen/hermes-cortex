### Critical: You need a poll cron to receive messages


The MCP client and config give you the **ability** to read messages, but nothing
actually checks the inbox automatically unless you have a **poll cron**. Without
it, messages sit unread until a human

> Moved from AGENTS.md by `agents-doc-audit.py --prune --apply`
> Date: 2026-07-02T07:11:47.553039+00:00
