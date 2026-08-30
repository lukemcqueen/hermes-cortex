# WAN Reachability Probe — Worked Example (2026-08-30)

Scenario: fleet operator couldn't reach a FreshTomato router's admin UI from outside. The test host sat behind the same router (the target was the LAN gateway itself).

Steps actually run, in order:

1. **LAN liveness** — `ping -c 2 <ROUTER_LAN_IP>` → 0% loss, ~0.6ms. `curl -sk -o /dev/null -w "%{http_code}" https://<ROUTER_LAN_IP>:8443/` → `401` (web UI up, auth gate responding — a live service, not a dead port).
2. **DDNS currency** — `dig +short <ddns-domain> A` matched `curl -s https://api.ipify.org` → A record current, not the problem.
3. **Hairpin attempts (inconclusive by design)** — `curl https://<PUBLIC_IP>:8443/` and `https://<ddns-domain>:8443/` from inside the LAN → HTTP 000 both. Note: these prove NOTHING about WAN reachability; do not stop here.
4. **External probes** via check-host.net free API, 2–3 nodes per port:
   - `443` → OPEN (web host)
   - `14007` → OPEN (health-endpoint host)
   - `11022` → OPEN (SSH host)
   - `10022` → Connection timed out (peer SSH — separate host issue)
   - `8443`, `8080`, `444`, `81`, `8444` → all timed out (router-admin candidate ports)
5. **Conclusion** — WAN forwarding healthy (3 sibling ports open from external nodes); router admin ports all closed externally → FreshTomato **remote admin disabled** (default). Fix: *Administration → Access → Remote Access* → enable web admin; reach afterward at `https://<ddns>:8443`.
6. **Side finding** — one forward (`10022`) down while siblings answered = that target host unreachable, NOT a router problem. Isolated by the contrast in step 4.

## Lesson

The single most valuable step is #4 done as a CONTRAST PAIR: probe the suspect port plus one known-good sibling port in the same pass. A mixed result splits the problem space (router vs target vs WAN) in one round-trip. Probing only the suspect port leaves the interpretation ambiguous.
