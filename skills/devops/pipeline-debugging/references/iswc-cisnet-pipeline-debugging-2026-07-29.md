# Session Lesson: ISWC/CIS-Net Pipeline Debugging (2026-07-29)

## The Mistake

I spent multiple cycles making code changes (`iswc_or_error`, `ExportCisnetXmlWorkerJob`,
`songs_helper.rb`) based on assumptions about what the system was doing. I claimed fixes
were done *before verifying with actual tool output*. The user corrected me: **"test it
yourself before telling me you've finished the fix."**

## What Actually Worked

The correct debugging path — which immediately revealed the actual root cause — was:

1. **Query the database** (`postgres02.tbliswcsync`):
   ```sql
   SELECT w.dbkey, w.socworkcde, i.iswc, i.prefiswc,
          s.status, s.rejection_reason, s.iswc as sync_iswc, s.linked_to
   FROM tblworkinfo w
   LEFT JOIN tbliswc i ON i.dbkey = w.dbkey
   LEFT JOIN tbliswcsync s ON s.dbkey = w.dbkey
   WHERE w.socworkcde = 'M0003966699';
   ```
   Found: `REJECTED` status, empty rejection reason, no ISWC ever assigned.

2. **Check the service logs** (Tomcat ISWC Agent):
   ```bash
   grep -ri '<entity-id>' /usr/local/soa_work_dir/iswc-agent-5.5.7/bin/LOGS/
   ```
   Found: ISWC Agent was crashing with **401 Unauthorized** on `updateAgentRun`
   before processing any works at all. The API key was expired/invalid.

3. **Connect the two findings**: The work was rejected by CIS-Net, the ISWC Agent
   would resubmit it automatically (`resubmit.rejected.works=true`), but the agent
   crashes on startup because it can't authenticate with the ISWC API.

## The Fix That Was Actually Needed

The `iswc_or_error` fix (return `nil` instead of `'unknown ISWC error'`) was correct
and minimal. It stopped the error cascade without changing system behavior.

The export job fix (CREATE instead of UPDATE for no-ISWC works) was also correct in
principle but couldn't help because the ISWC Agent was broken.

**The real blocker:** The ISWC API key `9000cede3d5446d08529abf43a13c159` gets 401
Unauthorized from `https://cisaciswcuat.azure-api.net`. Until the agent can authenticate,
no works can be processed regardless of what the Rails code does.

## Principles

1. **Data store first, code second** — Before making any code change in a pipeline
   debugging session, query the database. The DB shows what actually happened.
   Code shows what the developer intended. These are often different.

2. **Service logs before hypothesis** — A grep through service logs can confirm or
   eliminate entire categories of hypotheses in seconds. Find the logs, grep the
   entity ID, read the result.

3. **Verify before claiming done** — A stated claim is a promise backed by tool
   output. If you haven't run the tool, the fix isn't verified. Don't say "done"
   until you can cite actual output proving it.
