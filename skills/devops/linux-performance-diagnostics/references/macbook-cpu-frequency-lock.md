# MacBook CPU Frequency Firmware Lock

## Background

MacBooks running Linux (via the `applesmc` driver) have a known issue where the Apple System Management Controller (SMC) firmware can lock all CPU cores at the minimum P-state (~798-800 MHz) regardless of OS-level cpufreq settings. This manifests as a server that feels ~4x slower than expected under load.

## Case study: i7-4980HQ (Haswell, 4C/8T)

The session that produced this document was on a MacBook Pro with an Intel Core i7-4980HQ (2.8 GHz base, 4.0 GHz max, 47W TDP) running Linux Mint 6.14.0-29-generic.

## Diagnostic signature

All of these must be true simultaneously:

| Check | Symptom |
|-------|---------|
| `/proc/cpuinfo` MHz | All cores at exactly 798.x MHz |
| `scaling_cur_freq` | All cores at exactly 798.x MHz |
| Load average | High (e.g. 5.3 on 8 cores) — workload is waiting |
| Fans | Low (~2100 RPM) — contradicts the load level |
| Temps | Normal (53-56°C) — not thermal throttling |
| `scaling_driver` | Either `intel_pstate` or `intel_cpufreq` — driver swaps don't help |
| Governor changes | Accepted without error, no frequency change |
| `min_perf_pct = 100` | Accepted, no frequency change |
| `no_turbo` toggle | Accepted, no frequency change |
| `intel_pstate` active↔passive | Accepted, no frequency change |

## Attempted fixes (all failed)

The following were tried in order. Every OS-level write was accepted silently but produced zero frequency change:

1. `performance` governor (intel_cpufreq driver) — no change
2. `performance` governor (intel_pstate active driver) — no change
3. `schedutil` governor — no change
4. `ondemand` governor — no change
5. `userspace` governor — rejected (not available on intel_pstate)
6. `min_perf_pct = 100` — no change
7. `no_turbo` toggle (1 → 0) — no change
8. `intel_powerclamp` module unloaded — no change
9. `intel_pstate` toggled between active and passive — no change
10. RAPL PL1 clamp checked — not active, no change

The lock is at the firmware level, not the OS cpufreq subsystem.

## Resolution options

### Option 1: SMC reset (most effective)
Power off the MacBook. Press and hold Left Shift + Control + Option + Power for 10 full seconds. Release all keys. Power on normally. No data loss — the SMC reset only resets power management, thermal, and other hardware controllers.

### Option 2: Reboot
A simple warm reboot sometimes clears the firmware lock. If it reoccurs after a few days, the SMC reset is the more durable fix.

### Option 3: Kernel parameter `processor.max_cstate=1`
Prevents deep CPU C-states that may trigger the firmware lock. Add to `GRUB_CMDLINE_LINUX_DEFAULT` in `/etc/default/grub`, run `update-grub`, reboot. Trade-off: slightly higher idle power consumption.

### Option 4: Accept the constraint
At 800 MHz, the server still functions. llama-server takes ~4x longer per inference but produces correct results. Fans stay quiet, power draw is minimal. Document the lock as a known attribute of this hardware.

## NOPASSWD sudoers rules needed

To attempt the OS-level fixes, the following sudoers rules are required:

```
moses ALL=(root) NOPASSWD: /usr/bin/tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor
moses ALL=(root) NOPASSWD: /usr/bin/tee /sys/devices/system/cpu/intel_pstate/status
moses ALL=(root) NOPASSWD: /usr/bin/tee /sys/devices/system/cpu/intel_pstate/min_perf_pct
moses ALL=(root) NOPASSWD: /usr/bin/tee /sys/devices/system/cpu/intel_pstate/no_turbo
```

## Related

- [Intel P-State driver documentation](https://docs.kernel.org/admin-guide/pm/intel_pstate.html)
- [Apple SMC Linux driver](https://github.com/hwsensors/AppleSMC)
- Haswell/Broadwell MSR specification (Intel SDM Vol 4)
