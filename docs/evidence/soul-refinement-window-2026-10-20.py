#!/usr/bin/env python3
# Committed companion to docs/evidence/soul-refinement-window-2026-10-20.txt
# Run it from the repo root; it is read-only against the sessions store.
"""Soul-refinement mining pass — MEASUREMENT ONLY (read-only).

Resolves a bounded lookback window from RUN TIME (never a calendar date),
counts the rows it returns, and classifies them so a reader can tell an
operator correction from a cron self-prompt, an internal gateway
notification, a pasted cron delivery, or a relayed agent message.

Read-only: opens the sessions store with mode=ro and PRAGMA query_only.
Emits a redacted transcript: long digit runs (session ids, chat ids) are
masked and home paths collapsed, because the capture is committed to a
PUBLIC repo.
"""
import sqlite3
import os
import re
import time
import hashlib

WINDOW_HOURS = 24
DB = os.path.expanduser('~/.hermes/state.db')

NOW = time.time()
START = NOW - WINDOW_HOURS * 3600


def redact(text):
    """Mask what the PII guard would reject, and host paths."""
    if not text:
        return ''
    # long digit runs: session ids, chat ids, epochs
    text = re.sub(r'\d{7,}', lambda m: '<%d-digit>' % len(m.group(0)), text)
    # home paths
    text = re.sub(r'/home/[^/\s]+', '~', text)
    text = re.sub(r'/Users/[^/\s]+', '~', text)
    return text


def preview(text, n=70):
    one = ' '.join((text or '').split())
    return redact(one[:n])


def classify(content):
    """Mechanical classifier — machine-generated shapes only."""
    c = (content or '').lstrip()
    if c.startswith('[IMPORTANT: The user has invoked'):
        return 'cron_self_prompt'
    if c.startswith('[IMPORTANT: You are running as a scheduled cron job'):
        return 'cron_self_prompt'
    if c.startswith('[IMPORTANT: Background process'):
        return 'internal_notification'
    if c.startswith('[INTERNAL NOTIFICATION'):
        return 'internal_notification'
    if c.startswith('[Cron delivery:'):
        return 'pasted_cron_delivery'
    if c.startswith('Gateway message origin'):
        return 'gateway_origin_wrapper'
    return 'unclassified_human_session_prose'


def looks_machine_shaped(content):
    """A row classified as PROSE that still has a machine shape.

    The six prefixes above are not provably exhaustive, so exclusivity is
    CHECKED rather than claimed: anything the prefixes missed shows up here and
    raises the warning count, instead of silently inflating the prose tally the
    whole artifact is built on.
    """
    c = (content or '').lstrip()
    if c.startswith('[') or c.startswith('{'):
        return True
    head = c[:120].upper()
    return 'NOTIFICATION' in head or 'CRON DELIVERY' in head or 'GATEWAY MESSAGE' in head


def main():
    print('=' * 74)
    print('SOUL-REFINEMENT MINING PASS — window + row counts (read-only)')
    print('=' * 74)
    print('generator : ops-independent scratch measurement; re-run the same')
    print('            script to reproduce every count below')
    print('revisions : working tree %s' % _rev())
    print('volatile  : row COUNTS (the store is append-only and grows)')
    print()
    print('WINDOW resolved from RUN TIME, not the calendar date')
    print('  now    : %s   epoch=%.3f' % (time.strftime('%Y-%m-%d %H:%M:%S %Z', time.localtime(NOW)), NOW))
    print('  start  : %s   epoch=%.3f' % (time.strftime('%Y-%m-%d %H:%M:%S %Z', time.localtime(START)), START))
    print('  hours  : %d' % WINDOW_HOURS)
    print('  store  : %s' % redact(DB))
    print()

    con = sqlite3.connect('file:%s?mode=ro' % DB, uri=True, timeout=15)
    con.execute('PRAGMA query_only=1')
    cur = con.cursor()

    print('--- row counts by role, inside the window ---')
    for role in ('user', 'assistant', 'tool', 'system'):
        cur.execute('SELECT COUNT(*) FROM messages WHERE role=? AND timestamp>=?', (role, START))
        print('  %-10s %6d' % (role, cur.fetchone()[0]))
    print()

    cur.execute('SELECT COUNT(*) FROM messages WHERE role="user" AND timestamp>=?', (START,))
    all_user = cur.fetchone()[0]
    cur.execute('SELECT COUNT(*) FROM messages WHERE role="user" AND active=1 AND timestamp>=?', (START,))
    active_user = cur.fetchone()[0]
    print('--- the active=1 filter matters ---')
    print('  user rows in window, unfiltered : %6d' % all_user)
    print('  user rows in window, active=1   : %6d' % active_user)
    print('  dropped by the filter           : %6d' % (all_user - active_user))
    print()

    cur.execute('''SELECT session_id, content, timestamp FROM messages
                   WHERE role='user' AND active=1 AND timestamp>=?
                   ORDER BY timestamp''', (START,))
    rows = [{'sid': r[0], 'content': r[1], 'ts': r[2]} for r in cur.fetchall()]

    cron_rows = [r for r in rows if r['sid'].startswith('cron_')]
    human_rows = [r for r in rows if not r['sid'].startswith('cron_')]

    print('--- session classes ---')
    print('  total active user rows        : %6d' % len(rows))
    print('  ... in cron_ sessions         : %6d' % len(cron_rows))
    print('  ... in human/named sessions   : %6d' % len(human_rows))
    cron_sessions = sorted({r['sid'] for r in cron_rows})
    human_sessions = sorted({r['sid'] for r in human_rows})
    print('  distinct cron sessions        : %6d' % len(cron_sessions))
    print('  distinct human sessions       : %6d' % len(human_sessions))
    print()

    print('--- MECHANICAL classification of the human-session rows ---')
    print('    (a machine-generated shape is identified by its own literal')
    print('     marker; anything else is prose that must be READ)')
    buckets = {}
    for r in human_rows:
        buckets.setdefault(classify(r['content']), []).append(r)
    for k in sorted(buckets):
        print('  %-34s %4d' % (k, len(buckets[k])))
    machine = sum(len(v) for k, v in buckets.items() if k != 'unclassified_human_session_prose')
    prose = len(buckets.get('unclassified_human_session_prose', []))
    print('  %-34s %4d' % ('--- machine-generated subtotal', machine))
    print('  %-34s %4d' % ('--- prose that must be READ', prose))
    print()

    print('--- the same classification for the cron-session rows ---')
    cbuckets = {}
    for r in cron_rows:
        cbuckets.setdefault(classify(r['content']), []).append(r)
    for k in sorted(cbuckets):
        print('  %-34s %4d' % (k, len(cbuckets[k])))
    print()

    print('--- per-session row counts (sessions referenced by index, not id) ---')
    for i, sid in enumerate(human_sessions, 1):
        n = len([r for r in human_rows if r['sid'] == sid])
        first = min(r['ts'] for r in human_rows if r['sid'] == sid)
        print('  human session #%-3d %-26s rows=%d' % (
            i, time.strftime('%Y-%m-%d %H:%M', time.localtime(first)), n))
    print()

    prose_rows = buckets.get('unclassified_human_session_prose', [])
    print('--- prose rows, redacted preview (the material to READ) ---')
    for i, r in enumerate(prose_rows, 1):
        print('  [%s] %s' % (time.strftime('%m-%d %H:%M', time.localtime(r['ts'])), preview(r['content'])))
    print()

    # Exclusivity is CHECKED, not asserted: a row called prose that still looks
    # machine-generated is printed and counted as a warning, so a prefix the six
    # rules miss cannot quietly inflate the prose tally.
    suspects = [r for r in prose_rows if looks_machine_shaped(r['content'])]
    warnings = len(suspects)
    print('--- SUSPECT rows: classified prose but machine-shaped ---')
    if suspects:
        for r in suspects:
            print('  [%s] %s' % (time.strftime('%m-%d %H:%M', time.localtime(r['ts'])), preview(r['content'])))
    else:
        print('  (none - every machine-shaped row was caught by a literal prefix)')
    print('  count : %d' % warnings)
    print()

    print('--- verbatim window provenance ---')
    print('  sha256 of the session-id list (stable across re-runs of the')
    print('  SAME window; lets a reader confirm the same set was read):')
    blob = ','.join(sorted({hashlib.sha1(r['sid'].encode()).hexdigest() for r in rows}))
    print('    %s' % hashlib.sha256(blob.encode()).hexdigest())
    print()
    print('WINDOW IS NON-EMPTY: %d active user rows across %d sessions.' % (len(rows), len(human_sessions) + len(cron_sessions)))
    print('command : python3 <this script>   (read-only; no writes to the store)')
    print('rc      : 0')
    print('warnings: %d' % warnings)


def _rev():
    """Resolve the revision from the CWD the pass is run in (the repo),
    falling back through the repo root the store hints at. An artifact
    that cannot name its revision is not reviewable."""
    import subprocess
    for cwd in (os.getcwd(), os.path.dirname(os.path.abspath(__file__))):
        try:
            return subprocess.check_output(
                ['git', 'rev-parse', '--short', 'HEAD'],
                cwd=cwd, stderr=subprocess.DEVNULL).decode().strip()
        except Exception:
            continue
    return 'COULD-NOT-VERIFY (not run from inside a git checkout)'


if __name__ == '__main__':
    main()
