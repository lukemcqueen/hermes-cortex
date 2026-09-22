---
name: youtube-transcript
description: "Use when fetching a YouTube video transcript into text."
version: 1.0.0
category: media
---

# YouTube Transcript Fetching

Procedure for turning a YouTube URL into clean plain text for reading/summarizing.

## Procedure

1. **Check the installed yt-dlp version — `yt-dlp --version`.** If it is more than a
   few months old (distro/apt packages ship stale builds), YouTube's API rejects it
   with `HTTP 400 Bad Request / Precondition check failed` on every player client.
   The fix is a fresh install in a scratch venv, NOT apt:
   ```bash
   cd ~/.hermes/cache/scratch && python3 -m venv yenv
   ./yenv/bin/pip -q install -U yt-dlp
   ```
   PEP 668 blocks bare `pip install` — always use a venv (or `uv`).

2. **Check what captions exist:**
   `./yenv/bin/yt-dlp --list-subs <url>`
   - Output ending `has no subtitles` + a language list of "Available automatic
     captions" = no manual subs, but auto-generated captions DO exist — proceed.
   - Both empty = no transcript available; say so and stop.

3. **Download auto captions — `--skip-download` is REQUIRED.** Without it the tool
   aborts on format selection (YouTube often exposes only image/DRM formats to
   anonymous clients) and the subtitle file is never written, even though the
   subtitle URL itself works fine:
   ```bash
   ./yenv/bin/yt-dlp --skip-download --write-auto-subs \
     --sub-langs en --sub-format vtt -o <prefix> <url>
   ```
   A transient impersonation warning is harmless; the file still downloads.

4. **Strip the VTT to plain text** (drop timestamp lines, tags, and the duplicated
   rolling-caption lines):
   ```python
   import re
   lines = open(f'{prefix}.en.vtt').read().splitlines()
   out = []
   for l in lines:
       if '-->' in l or l.strip() in ('WEBVTT', '') or l.startswith(('Kind:', 'Language:', 'NOTE')):
           continue
       l = re.sub(r'<[^>]+>', '', l).strip()
       if l and (not out or out[-1] != l):
           out.append(l)
   open('transcript.txt', 'w').write(' '.join(out))
   ```

5. **Get metadata** for context before summarizing:
   `./yenv/bin/yt-dlp --skip-download --print "%(title)s | %(channel)s | %(upload_date)s | %(duration_string)s" <url>`

6. **Reading a long transcript (>~30 min):** split it into ~8 word-wrapped segments
   (~12K chars each) into files and `read_file` them one at a time — a single
   `read_file` on the whole file truncates. Auto-transcripts garble proper nouns
   (product/person names become plausible wrong words) — flag suspected name
   garbling instead of confidently repeating the wrong name.

## Pitfalls

- **Never diagnose the stale-distro yt-dlp as 'YouTube is down'.** The 400 errors
  name a Precondition failure and every player client fails identically — that is
  an old-extractor signature; upgrade before anything else.
- **`-f none` is not a substitute for `--skip-download`** — it still enters format
  selection and fails the run without writing captions.
- **Manual subs and auto captions are different tracks.** `--write-subs` gets
  nothing when only auto captions exist; use `--write-auto-subs`.
- **Write scratch venvs/files under `~/.hermes/cache/scratch`** (pruned, not
  user-visible clutter) — do not litter the home directory.
