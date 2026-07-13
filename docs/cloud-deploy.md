# Cloud Deployment Runbook — Hermes Cortex

Deploy a Hermes Cortex agent to a cloud VM (AWS EC2 or Hetzner Cloud).
Local/private-first — this enables migration when needed, not a replacement for local operation.

---

## Prerequisites

- A domain name (DNS managed by your provider)
- Cloud provider account (AWS or Hetzner)
- SSH key pair
- API keys for your LLM provider(s)

---

## AWS EC2 Deployment

### 1. Launch Instance

| Setting | Value |
|---------|-------|
| **AMI** | Ubuntu 24.04 LTS (amd64) |
| **Instance** | `t3.medium` (2 vCPU, 4GB RAM) — minimum for Ollama + Langfuse |
| **Storage** | 40GB gp3 root volume — extend to 100GB+ if pulling large models |
| **Security Group** | See ports below |
| **User data** | Paste `ops/deploy/cloud-init.yaml` content |
| **IAM role** | None required (optional: SSM for session manager) |

### 2. Security Group Rules

| Direction | Port | Source | Purpose |
|-----------|------|--------|---------|
| Inbound | 22 | Your IP | SSH |
| Inbound | 80 | 0.0.0.0/0 | HTTP (for Let's Encrypt ACME challenge) |
| Inbound | 443 | 0.0.0.0/0 | HTTPS |
| Inbound | 13001 | Fleet IPs or internal CIDR | Cortex Dashboard |
| Inbound | 13002 | Fleet IPs or internal CIDR | Langfuse |
| Inbound | 13004 | Fleet IPs or internal CIDR | Agent Inbox API |
| Inbound | 13005 | Fleet IPs or internal CIDR | Hermes UI |
| Inbound | 13007 | Fleet IPs or internal CIDR | Health endpoint |

> **Security note:** Agent service ports (13001–13007) should be restricted to your fleet's CIDR or use a VPN/VPC peering. Only ports 22, 80, 443 need to be open to the internet.

### 3. Elastic IP

1. Allocate an Elastic IP in the same region
2. Associate it with the EC2 instance
3. Point your DNS `A` record to this IP

### 4. DNS Setup

```
yourdomain.com.    A     → <Elastic-IP>
*.yourdomain.com.  A     → <Elastic-IP>   (optional, for subdomains)
```

---

## Hetzner Cloud Deployment

### 1. Create Server

| Setting | Value |
|---------|-------|
| **Image** | Ubuntu 24.04 LTS |
| **Type** | `CX32` (4 vCPU, 8GB RAM) — recommended |
| **Volume** | 50GB + 50GB additional volume for models |
| **Firewall** | See rules below |
| **Cloud Config** | Paste `ops/deploy/cloud-init.yaml` content |
| **Backups** | Enable (€1.20/month) |

### 2. Firewall Rules

Same port map as AWS security group above. Create a Hermes Cortex firewall template:

```bash
hcloud firewall create --name hermes-cortex
hcloud firewall add-rule hermes-cortex --direction in --protocol tcp --port 22 --source-ips 0.0.0.0/0 --description SSH
hcloud firewall add-rule hermes-cortex --direction in --protocol tcp --port 80 --source-ips 0.0.0.0/0 --description HTTP
hcloud firewall add-rule hermes-cortex --direction in --protocol tcp --port 443 --source-ips 0.0.0.0/0 --description HTTPS
# Agent ports restricted to fleet
hcloud firewall add-rule hermes-cortex --direction in --protocol tcp --port 13001-13007 --source-ips <your-fleet-cidr>
```

### 3. Additional Volume (for models)

```bash
# Mount at /mnt/models — symlink Ollama's model dir
mkdir -p /mnt/models
mkfs.ext4 /dev/sdb
mount /dev/sdb /mnt/models
ln -sf /mnt/models /home/ubuntu/.ollama/models
echo '/dev/sdb /mnt/models ext4 defaults,nofail 0 2' >> /etc/fstab
```

---

## Post-Bootstrap Setup

### 1. SSH In

```bash
ssh ubuntu@<server-ip>
```

### 2. Configure Secrets

```bash
nano ~/hermes-cortex/.env
```

Required variables — set every one:

| Variable | Example | Source |
|----------|---------|--------|
| `CORTEX_HEALTH_URL` | `https://yourdomain.com:13007/health` | Your domain + port |
| `CORTEX_INBOX_URL` | `https://yourdomain.com:13004` | Your domain + port |
| `CORTEX_INBOX_AUTH` | `moses:your-generated-password` | Fleet admin |
| `AGENT_NAME` | `moses` | Match inbox auth user |
| `IS_ORCHESTRATOR` | `false` | `true` only for Moses/Esther |
| `OPENROUTER_API_KEY` | `sk-or-...` | openrouter.ai |
| `DEEPSEEK_API_KEY` | `sk-...` | platform.deepseek.com |
| `HERMES_LANGFUSE_PUBLIC_KEY` | `pk-lf-...` | Langfuse project settings |
| `HERMES_LANGFUSE_SECRET_KEY` | `sk-lf-...` | Langfuse project settings |
| `CORTEX_SSL_CERT_PATH` | `/etc/letsencrypt/live/.../fullchain.pem` | certbot output |
| `CORTEX_SSL_CERT_KEY_PATH` | `/etc/letsencrypt/live/.../privkey.pem` | certbot output |
| `JUDGE_MODEL` | `qwen2.5-coder:3b` | Local or API model |
| `EMBEDDING_MODEL` | `nomic-embed-text:v1.5` | Local Ollama model |
| `LLM_CRON_MODEL` | `deepseek-v4-flash` | API model |
| `LLM_CRON_PROVIDER` | `deepseek` | Provider name |

### 3. Run Installer

```bash
cd ~/hermes-cortex
bash ops/install/install.sh
```

### 4. Verify

```bash
python3 ops/scripts/manage/cortex-doctor.py
```

Expected: all checks pass (or acceptable warnings).

### 5. Configure SSL (Let's Encrypt)

```bash
sudo certbot --nginx -d yourdomain.com
sudo systemctl reload nginx
```

If using subdomains per service:

```bash
sudo certbot --nginx -d yourdomain.com -d dashboard.yourdomain.com -d langfuse.yourdomain.com
```

---

## Verification Checklist

- [ ] `cortex-doctor.py` passes with no FAIL reports
- [ ] Ollama responds: `curl http://127.0.0.1:11434/api/tags`
- [ ] Health endpoint: `curl https://yourdomain.com:13007/health`
- [ ] Dashboard accessible: `https://yourdomain.com:13001`
- [ ] Langfuse accessible: `https://yourdomain.com:13002`
- [ ] Agent can pull models: `ollama pull nomic-embed-text:v1.5`
- [ ] `hermes cron list` shows all expected cron jobs
- [ ] `.env` has `chmod 600` and all secrets filled
- [ ] UFW active: `sudo ufw status`
- [ ] Certificates valid: `sudo certbot certificates`

---

## Scaling Notes

| Scenario | Action |
|----------|--------|
| More CPU for Ollama | Upgrade instance type (t3.large, CX42) |
| More models | Add EBS/volume, symlink `~/.ollama/models` to it |
| Dedicated Langfuse DB | Use RDS (PostgreSQL) + ClickHouse Cloud instead of Docker |
| High availability | Run two agents behind nginx upstream block |
| CI/CD auto-deploy | Use `ops/deploy/ansible/` playbook |

---

## Cost Estimate (Approximate)

| Provider | Instance | Monthly |
|----------|----------|---------|
| **AWS** | t3.medium + 40GB gp3 | ~$35–45 |
| **AWS** | t3.large + 100GB gp3 | ~$55–70 |
| **Hetzner** | CX32 + 50GB volume | ~$12–18 |
| **Hetzner** | CX42 + 100GB volume | ~$22–30 |

Hetzner is significantly cheaper for equivalent specs — recommended for self-hosted agent fleets.

---

## Recovery

If the server is lost:

1. Launch a new instance with the same cloud-init
2. Restore `.env` from your private secrets backup
3. Re-pull models: `ollama pull nomic-embed-text:v1.5`
4. Point DNS to new IP
5. Re-run certbot

Full recovery time: ~15 minutes (mostly model downloads).
