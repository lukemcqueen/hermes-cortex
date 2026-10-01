# Cron expr → systemd OnCalendar translation

Converting a 5-field cron expression to a systemd `OnCalendar=` value for a user timer unit. **Always validate the generated value** with `systemd-analyze calendar '<expr>'` (assert rc=0 and `Normalized form:` in stdout) BEFORE shipping — a step-position typo passes a naive generator silently and the timer never fires.

## Syntax map (verified on systemd-analyze)

| Cron expr | Meaning | Correct OnCalendar | Wrong form to avoid |
|---|---|---|---|
| `* * * * *` | every minute | `*-*-* *:*:00` | — |
| `*/N * * * *` | every N minutes | `*-*-* *:0/N:00` | `*/N:00` (hourly, not minute) |
| `0 */N * * *` / `* */N * * *` | every N hours at :00 | `*-*-* *:00/N:00` | `*/N:00:00` (rejected by systemd) |
| `M * * * *` / `0 * * * *` | every hour at minute M | `*-*-* *:MM:00` | — |
| `M H * * *` | daily at H:MM | `*-*-* HH:MM:00` | — |
| `M H1,H2 * * *` | at listed hours | `*-*-* HH1,HH2:MM:00` | hour list must be zero-padded `HH` |
| `M H1-H2 * * *` | every hour in range | `*-*-* HH1..HH2:MM:00` | range separator is `..` not `-` |
| `M H * * D` | weekly on D | `Sun,Mon.. *-*-* HH:MM:00` | day tokens `Mon..Fri`, lists `Mon,Sat` |
| `M H * * 1-5` | weekdays | `Mon..Fri *-*-* HH:MM:00` | — |
| `every 5m`/`10m` | minute interval (60%N==0) | `*-*-* *:0/N:00` | — |
| `every 2h`/`360m` | hour interval | `*-*-* *:00/N:00` | — |

## Rules that cost a mistake

- **Hourly step is `*:00/N:00`, NOT `*/N:00:00`** — the latter is `Invalid argument` in `systemd-analyze`. Feels right, is wrong.
- **Minute step is `*:0/N:00`** (colon-zero-slash-N), not `*/N:00`. `*/N:00` is an hourly step.
- **Ranges use `..`** (`09..18`), lists use `,` (`11,17`); zero-pad hours (`09` not `9`).
- **Day-of-week**: 0/7=Sun…6=Sat; `1-5` → `Mon..Fri`, hour lists zero-pad.
- **Only map what you're sure of** — non-dividing minute intervals (e.g. `70m`) refuse rather than under-fire.
- **Validate every distinct generated value in batch**: collect all OnCalendar values from `jobs.json`, loop `systemd-analyze calendar` over them, count accept/reject — a generator that maps 60/60 *phrases* may still show zero `Normalized form:` if you grep the wrong substring (`normalized:` vs `Normalized form:`); assert the actual marker.

## The validator snippet

```python
import subprocess
ok = bad = 0
for v in sorted(values):
    r = subprocess.run(['systemd-analyze','calendar',v],capture_output=True,text=True)
    if r.returncode==0 and 'Normalized form:' in r.stdout: ok += 1
    else: bad += 1
print(f'valid {ok}/{len(values)}, rejected {bad}')
```

Also run `systemd-analyze verify <job>.service <job>.timer` for unit-level correctness, and confirm `systemctl --user list-timers` shows the unit active with the expected next-elapse.
