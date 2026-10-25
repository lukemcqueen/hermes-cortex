hermes-cortex=framework ONLY; repo plugins/ truth; push: commit→cortex-update.sh→push.
§
Esther: orchestrator (hot backup), HAS cronjob. hc send: liveness+dedup --force, needs --self-tested; bus subjects UPPER_CASE [A-Z0-9_] only (prose→HTTP 400). Moses ssh mosesaaron (192.168.1.24); AGENTS/SOUL edits need approval.
§
Esther local PG=REPORTS MIRROR (stale): BusClient/archive hits IT, not moses → verify queue via ssh mosesaaron; metrics :14005.
§
Secrets/network: Spotify ~/.spotify_user (never print, subshell-read only); router 192.168.1.1:8443 cred ~/.asus, status-devices.asp=arplist+dhcpd_lease, 2 leases ~10min=alive, zero-MAC=VM; PII: phone/private IPs/surnames generalize, GH handle guard-blocked — keep pseudonym.
§
Laptop=2012 MBP15 Retina. Kepler→nvidia-470 ONLY, reboot=pci. Display unused/SSH→1080p@60 all 3 layers: ~/.xprofile+autostart+lightdm.conf.d/50-hdmi-1080p.conf. macbook-linux-maintenance skill FIRST.
§
Fleet-doc: shared docs=fleet DEFAULTS; per-host dev local; .env at deploy root.
§
sudo NOPASSWD nft/iptables BROKEN (re-confirmed 10-12): sudo -n needs a password — re-verify.
§
Cron/script quirks: bare invocation=cron mode; sqlite close ALL paths (finally+rollback) else 'database is locked'. Review material must be CONTENT not a path (a path gets a hollow CLEAN); cron commits need skill_view('reflexion-check') first; the repo SOUL template is write-refused in cron, the deployed copy is not.
§
steadfaste build: deepseek-v4-flash-free basic, v4-pro only design/review.
§
Deploy/interop: register map per-file NOT derivable — use ~/.hermes-cortex/deploy-manifest.tsv + cortex_lib.paths.resolve_repo_resource, verify on DEPLOYED tree. N agents → ONE impl + per-host adapters (docs/design/agent-interop.md). Failing assertion → check the PROBE first.
§
Luke 2026-10-14, STANDING: 'I don't trust your judgment. Have deepseek pro ALWAYS review your plan BEFORE building.' Submit the PLAN to the GOVERNED reviewer first: ops/scripts/orch-bus/adversarial-review.py --cycle-id N --review (rows in adversarial_reviews, 1/cycle); prose-only plans are refused as unverified-claim — include code/output.