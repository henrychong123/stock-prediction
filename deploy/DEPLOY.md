# StockSight Production Deployment

Step-by-step guide for deploying to an Oracle Cloud ARM VM (Ubuntu 22.04) with nginx + Let's Encrypt HTTPS + systemd timers for scheduled jobs + Google OAuth for login.

Written for a fresh VM. Run commands as the `ubuntu` user via `sudo` where noted.

---

## When to use this guide vs. ngrok

This guide is for a **proper 24/7 deployment** — VM, domain, HTTPS cert, systemd timers, hands-off uptime. Use it when the dashboard needs to be reachable to others continuously.

If you just want **occasional remote access** to your already-running Windows machine (no VPS, no domain, no nginx), use ngrok instead — see the "Remote Access" section in `README.md`. The 35 `StockPred-*` Windows scheduled tasks keep the SQLite DB fresh, and `start-tunnel.bat` exposes the local Flask app at a stable HTTPS URL. Auth (Google OAuth + `ALLOWED_EMAILS`) is the same in both setups, so the public URL is safe to share. The tradeoff is that the dashboard is only reachable while your PC is on.

---

## 0. Prerequisites

- Oracle Cloud Always Free VM (VM.Standard.A1.Flex ARM 4 OCPU / 24 GB is ideal; VM.Standard.E2.1.Micro works but is tight)
- A domain name pointing at the VM's public IP (DuckDNS is free and supported; any A record works)
- Google Cloud OAuth client configured for **production redirect URI**: `https://yourdomain.com/login/google/authorized`

### Oracle Security List + VCN firewall

On Oracle's web console: VCN → Security Lists → Default Security List → add **ingress** rules:
- TCP port 80 from 0.0.0.0/0
- TCP port 443 from 0.0.0.0/0
- TCP port 22 from 0.0.0.0/0 (or your IP only)

Oracle Ubuntu images also have iptables rules blocking 80/443 by default — `setup.sh` handles this.

---

## 1. Initial VM setup (one command)

```bash
ssh ubuntu@<your-vm-ip>
sudo apt update
git clone https://github.com/henrychong123/stock-prediction.git /tmp/stocksight
sudo mv /tmp/stocksight /opt/stocksight
sudo chown -R ubuntu:ubuntu /opt/stocksight
cd /opt/stocksight
sudo bash deploy/setup.sh
```

`setup.sh` installs Python 3.11, nginx, certbot, Node.js, Claude Code CLI, creates the `stocksight` user, sets up the Python venv, installs systemd units, opens the firewall. Takes ~5 minutes.

---

## 2. Authenticate Claude Code CLI

The `stocksight-shortterm-reason` timer invokes `claude -p` — needs a logged-in Claude CLI.

```bash
sudo -u stocksight claude login
```

This prints a device-code URL. Open it on your laptop, approve, paste the returned token. Now `sudo -u stocksight claude --version` confirms auth.

---

## 3. Install Playwright browsers

The shortterm scraper uses Chromium headless.

```bash
sudo -u stocksight bash -c '
    cd /opt/stocksight
    source venv/bin/activate
    playwright install chromium
    playwright install-deps  # may prompt for apt install
'
```

If `install-deps` fails, run manually:
```bash
sudo apt install -y libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
    libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 \
    libgbm1 libxshmfence1 libasound2
```

---

## 4. Configure `.env`

Create `/opt/stocksight/.env` (owned by `stocksight:stocksight`, mode `0600`):

```bash
sudo -u stocksight nano /opt/stocksight/.env
```

Contents:

```ini
# --- Flask session / auth ---
FLASK_SECRET_KEY=<run: python3 -c "import secrets; print(secrets.token_hex(32))">
SESSION_COOKIE_SECURE=1
TRUST_PROXY=1

# Google OAuth (production client, redirect URI = https://YOUR_DOMAIN/login/google/authorized)
GOOGLE_OAUTH_CLIENT_ID=<paste>
GOOGLE_OAUTH_CLIENT_SECRET=<paste>
ALLOWED_EMAILS=your.email@gmail.com,friend1@gmail.com,friend2@gmail.com

# DO NOT set OAUTHLIB_INSECURE_TRANSPORT in production — prod uses HTTPS.

# --- Data APIs (existing) ---
FINNHUB_API_KEY=<paste>
REDDIT_CLIENT_ID=<paste>
REDDIT_CLIENT_SECRET=<paste>
NEWSAPI_KEY=<paste>
```

Permissions:
```bash
sudo chown stocksight:stocksight /opt/stocksight/.env
sudo chmod 600 /opt/stocksight/.env
```

---

## 5. Copy data from your Windows machine

Skip this if starting fresh — the first scheduled runs will populate everything within a day.

On Windows (PowerShell):
```powershell
scp D:\stock-prediction\data\predictions.db ubuntu@<vm-ip>:/tmp/
scp -r D:\stock-prediction\models ubuntu@<vm-ip>:/tmp/
scp D:\stock-prediction\AGENT.md D:\stock-prediction\SKILL.md D:\stock-prediction\MEMORY.md ubuntu@<vm-ip>:/tmp/
```

On the VM:
```bash
sudo mv /tmp/predictions.db /opt/stocksight/data/
sudo mv /tmp/models/* /opt/stocksight/models/
sudo mv /tmp/AGENT.md /tmp/SKILL.md /tmp/MEMORY.md /opt/stocksight/
sudo chown -R stocksight:stocksight /opt/stocksight/data /opt/stocksight/models \
    /opt/stocksight/AGENT.md /opt/stocksight/SKILL.md /opt/stocksight/MEMORY.md
```

---

## 6. Configure domain + HTTPS

### A. Point DNS at the VM

Update your A record: `yourdomain.com` → VM public IP. Wait for propagation (`dig yourdomain.com` returns the VM IP).

### B. Update nginx config

```bash
sudo sed -i 's/stocksight.duckdns.org/yourdomain.com/' /etc/nginx/sites-available/stocksight
sudo nginx -t && sudo systemctl reload nginx
```

### C. Get Let's Encrypt cert

```bash
sudo certbot --nginx -d yourdomain.com
```

Certbot prompts for email, accepts terms, auto-modifies nginx to add port 443 + cert paths + HTTP → HTTPS redirect. Renews automatically via systemd timer.

---

## 7. Start services

```bash
sudo systemctl start stocksight-web.service
sudo bash /opt/stocksight/deploy/scripts/start-all.sh
```

Verify:
```bash
systemctl list-timers 'stocksight-*' --no-pager
systemctl status stocksight-web
```

All 9 timers should show `active (waiting)` with a `NEXT` time. `stocksight-web` should show `active (running)`.

---

## 8. Smoke test

From your laptop:

```bash
curl -I https://yourdomain.com/                   # expect 302 → /login
curl -I https://yourdomain.com/login              # expect 200
curl -I https://yourdomain.com/api/shortterm/latest  # expect 401
```

Then in browser: `https://yourdomain.com/` → redirected to `/login` → click "Sign in with Google" → allowed email: sees dashboard; non-allowed email: sees "Access denied".

---

## 9. Cutover — disable Windows Task Scheduler

Once the VM has run for 24h without issues and produced its own `shortterm_picks`, **disable the Windows-side scheduled tasks** so they don't compete for Claude credits and DB writes:

```powershell
# On Windows, in PowerShell as admin:
$tasks = @(
    "StockPred-PriceTracker",
    "StockPred-NewsTracker",
    "StockPred-CatalystScan",
    "StockPred-SocialCollector",
    "StockPred-DailyCollector",
    "StockPred-BatchPredict",
    "StockPred-ShorttermScrape",
    "StockPred-ShorttermReason-Morning",
    "StockPred-ShorttermReason-Midday",
    "StockPred-ShorttermReason-Close",
    "StockPred-ShorttermReason-Eve",
    "StockPred-ShorttermEval"
)
foreach ($t in $tasks) { schtasks /change /TN $t /DISABLE }
```

(Use `/delete /f` instead of `/change /DISABLE` if you're confident you won't roll back.)

---

## Operations

### Trigger a job manually (for testing)

```bash
sudo systemctl start stocksight-shortterm-scrape.service    # run the scraper once
sudo systemctl start stocksight-shortterm-reason.service    # run the reasoner once
sudo systemctl start stocksight-shortterm-eval.service      # run the evaluator once
```

### Watch logs

```bash
journalctl -u stocksight-web -f                              # web app logs live
journalctl -u stocksight-shortterm-reason.service --since today   # today's reasoning
tail -f /var/log/stocksight/web-access.log                   # Gunicorn access log
```

### Database backups

`stocksight-backup.timer` runs daily. Output lives under `/opt/stocksight/backups/`. The script at `deploy/scripts/backup-db.sh` is what runs — edit it to change retention or destination.

### Updating the code

```bash
cd /opt/stocksight
sudo -u stocksight git pull
sudo -u stocksight bash -c 'source venv/bin/activate && pip install -r requirements.txt'
sudo systemctl restart stocksight-web
```

If systemd units changed, also:
```bash
sudo cp deploy/systemd/*.service deploy/systemd/*.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl restart stocksight-shortterm-scrape.timer stocksight-shortterm-reason.timer stocksight-shortterm-eval.timer
```

### Adding / removing allowed emails

Edit `/opt/stocksight/.env`, update `ALLOWED_EMAILS=`, then:
```bash
sudo systemctl restart stocksight-web
```
(No rebuild needed; the env file is re-read on restart.)

### Adding a friend after launch

1. Add their email to `ALLOWED_EMAILS` in `.env`
2. Restart `stocksight-web`
3. Also add their email as a "test user" in Google Cloud OAuth consent screen, otherwise Google rejects their login because the app is still in "testing" mode. If you have ≥10 test users you plan to keep, publish the app (OAuth consent → Publish — no Google review needed for small apps).

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Login redirects to Google, comes back with "redirect_uri_mismatch" | OAuth client doesn't list this exact URL | Add `https://yourdomain.com/login/google/authorized` in Google Cloud → Credentials → OAuth client |
| `/login` returns 500 with `SECRET_KEY not set` | `.env` missing `FLASK_SECRET_KEY` | Add it; restart `stocksight-web` |
| OAuth succeeds but Flask says "authentication required" loop | SameSite=Lax + scheme mismatch | Set `TRUST_PROXY=1` in `.env`, restart `stocksight-web` |
| `stocksight-shortterm-reason` fails with `Claude CLI not found` | Reasoner ran before `claude login` completed, OR claude not on stocksight user's PATH | Re-run `sudo -u stocksight claude login`; verify with `sudo -u stocksight which claude` |
| Scraper times out | Chromium system deps missing | `sudo playwright install-deps` or apt install the libnss/libatk/libxkb packages listed in step 3 |
| Certbot fails "connection refused on :80" | Oracle iptables still blocking | `sudo iptables -L INPUT -n | grep 80`; if empty, re-run setup.sh step 4 |
| POST routes return 401 when logged in | CSRF cookie issue, or session cookie not persisting over HTTPS | Check `SESSION_COOKIE_SECURE=1` only in prod; check browser dev tools → cookies |

---

## What this deployment is NOT

- **Not a high-availability setup**: single VM, single SQLite file. If the VM dies, serve 502s until reboot. Fine for friends-only.
- **Not auto-scaling**: Gunicorn runs 3 workers. Handles maybe 30 concurrent users before latency rises.
- **Not backup-to-another-region**: the backup timer writes to the same disk. For off-site backup, edit `backup-db.sh` to also upload to S3/rclone/etc.
- **Not fully CSRF-protected**: SameSite=Lax cookies block most CSRF but a strict app should add Flask-WTF. Pending.
