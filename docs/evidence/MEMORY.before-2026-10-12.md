hermes-cortex=framework ONLY (08-24); repo plugins/ truth; push: commit→cortex-update.sh→push.
§
Esther: orchestrator (hot backup). HAS cronjob. hc send: liveness+dedup --force, needs --self-tested; bus subjects MUST be UPPER_CASE [A-Z0-9_] (prose→HTTP 400, detail hidden). Moses ssh mosesaaron (192.168.1.24). AGENTS/SOUL edits: approval.
§
Esther local PG=REPORTS MIRROR (stale): Python BusClient/archive hits IT, not moses → verify queue state via ssh mosesaaron; metrics :14005.
§
PII guard: phone/private IPs/surnames → generalize; GH handle guard-blocked — repo keeps pseudonym.
§
Router 192.168.1.1:8443 cred ~/.asus. status-devices.asp: arplist+dhcpd_lease; 2 leases ~10min=alive; zero-MAC=VM.
§
Spotify creds ~/.spotify_user: never print, subshell-read only.
§
Laptop=2012 MBP15 Retina. Kepler→nvidia-470 ONLY, reboot=pci. Display unused/SSH→1080p@60 all 3 layers: ~/.xprofile+autostart+lightdm.conf.d/50-hdmi-1080p.conf. macbook-linux-maintenance skill FIRST.
§
Fleet-doc: shared docs=fleet DEFAULTS; per-host dev local; .env at deploy root.
§
sudo NOPASSWD nft/iptables BROKEN (09-28): sudo -n needs a password — re-verify before relying on it.
§
Luke cron dedup: identical deliveries=noise → suppress via state-signature in delivery layer.
§
steadfaste build: deepseek-v4-flash-free for basic tasks, v4-pro only for design/review.
§
Script crons: bare invocation=cron mode (create_cron has no args; argparse exit2→3-strike pause). sqlite: close ALL paths (finally+rollback) or 'database is locked'; dup row=benign rc0.
§
Interop (standing, Luke 10-02): design for N coding agents — ONE impl (context_tools TOOLS+HANDLERS+dispatch), per-host ADAPTERS with no semantics, schemas DERIVED not hand-written; docs/design/agent-interop.md. Failing assertion → check the PROBE first (wrapped phrase, comment-vs-code, wrong detector, test race) — code was right 3x in one night.
§
Deploy: register map per-file, NOT derivable → deploy-manifest.tsv + cortex_lib.paths.resolve_repo_resource; never guess a path. Verify on DEPLOYED tree.
