# Server Setup Guide

Complete instructions to set up the VWAP-EMA trading bot on a new server.

---

## Current Server Details

| Item | Value |
|------|-------|
| Provider | DigitalOcean |
| IP | 64.227.163.187 |
| OS | Ubuntu 24.04.3 LTS |
| Python | 3.12.3 |
| Timezone | Asia/Kolkata (IST) |
| SSH Key | ~/.ssh/id_ed25519_ai_dev |

---

## Step-by-Step Setup for New Server

### 1. SSH into new server
```bash
ssh -i ~/.ssh/YOUR_KEY root@NEW_SERVER_IP
```

### 2. Update system and install dependencies
```bash
apt update && apt upgrade -y
apt install -y python3 python3-pip python3-venv git
```

### 3. Set timezone to IST
```bash
timedatectl set-timezone Asia/Kolkata
```

### 4. Create project directory
```bash
mkdir -p /root/ema_vwap
cd /root/ema_vwap
```

### 5. Create Python virtual environment
```bash
python3 -m venv venv
source venv/bin/activate
```

### 6. Install Python packages
```bash
pip install pandas numpy requests python-dotenv
```

**Full package list (pip freeze):**
```
certifi==2026.2.25
charset-normalizer==3.4.7
idna==3.12
numpy==2.4.4
pandas==3.0.2
python-dateutil==2.9.0.post0
python-dotenv==1.2.2
requests==2.33.1
six==1.17.0
urllib3==2.6.3
```

### 7. Copy project files from local machine
```bash
# Run from your local machine
scp -i ~/.ssh/YOUR_KEY /Users/umesh.kedimi/ema_vwap/*.py root@NEW_SERVER_IP:/root/ema_vwap/
scp -i ~/.ssh/YOUR_KEY /Users/umesh.kedimi/ema_vwap/*.md root@NEW_SERVER_IP:/root/ema_vwap/
scp -i ~/.ssh/YOUR_KEY /Users/umesh.kedimi/ema_vwap/*.csv root@NEW_SERVER_IP:/root/ema_vwap/
scp -i ~/.ssh/YOUR_KEY /Users/umesh.kedimi/ema_vwap/*.env root@NEW_SERVER_IP:/root/ema_vwap/
```

### 8. Set up cron job
```bash
crontab -e
```

Add this line:
```
10 9 * * 1-5 cd /root/ema_vwap && /root/ema_vwap/venv/bin/python vwap_ema_signal.py >> /root/bot.log 2>&1
```

**Cron explanation:**
- `10 9` = 9:10 AM
- `* * 1-5` = Monday to Friday
- `>> /root/bot.log 2>&1` = Append output to log file

### 9. Update config.env with fresh tokens
```bash
nano /root/ema_vwap/config.env
# Update FYERS_ACCESS_TOKEN and KITE_ACCESS_TOKEN
```

### 10. Test run
```bash
cd /root/ema_vwap
source venv/bin/activate
python vwap_ema_signal.py
# Press Ctrl+C after verifying it starts correctly
```

---

## Project Files

| File | Purpose |
|------|---------|
| `vwap_ema_signal.py` | Main bot - signal detection (historical mode) |
| `trade_manager.py` | Trade rules, breakeven, P&L tracking |
| `option_selector.py` | Strike selection (delta/premium mode) |
| `kite_api.py` | Zerodha order execution |
| `review_signals.py` | Post-market signal analysis |
| `config.env` | All configuration (tokens, parameters) |
| `trade_journal.csv` | Trade records |
| `LEARNINGS.md` | Documented learnings |
| `CLAUDE.md` | AI assistant context |

---

## Config.env Template

```env
# Kite Connect (Zerodha) - for Orders & Quotes
KITE_API_KEY=your_api_key
KITE_API_SECRET=your_api_secret
KITE_ACCESS_TOKEN=UPDATE_DAILY

# Fyers API v3 Credentials - for Signal Data (Candles)
FYERS_ID=your_fyers_id
FYERS_APP_ID=your_app_id
FYERS_SECRET_KEY=your_secret_key
FYERS_REDIRECT_URI=https://trade.fyers.in/api-login/redirect-uri/index.html
FYERS_ACCESS_TOKEN=UPDATE_DAILY

# Telegram Bot Configuration
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id

# Trading Configuration
SYMBOL=NSE:NIFTY50-INDEX
EMA_PERIOD=5
SCAN_START_TIME=09:25
SCAN_END_TIME=15:15

# Trade Execution Settings
TRADING_ENABLED=true
PAPER_TRADING=false

# Trade Timing
TRADE_START_TIME=09:30
TRADE_END_TIME=14:30
FORCE_CLOSE_TIME=15:15

# Trade Parameters
MAX_TRADES_PER_DAY=1
TARGET_POINTS=80
STOPLOSS_POINTS=25
LOT_SIZE=65

# Option Selection
STRIKE_MODE=delta
MIN_PREMIUM=220
ITM_OFFSET_FOR_DELTA=150
MAX_ITM_OFFSET=300
```

---

## Daily Token Update Script

Save as `update_tokens.sh` on local machine:

```bash
#!/bin/bash
SERVER="root@NEW_SERVER_IP"
SSH_KEY="~/.ssh/YOUR_KEY"
CONFIG_PATH="/root/ema_vwap/config.env"

echo "Token Update for Trading Bot"
echo "=============================="

read -p "Paste FYERS access token: " FYERS_TOKEN
read -p "Paste KITE access token: " KITE_TOKEN

if [ -z "$FYERS_TOKEN" ] || [ -z "$KITE_TOKEN" ]; then
    echo "Error: Both tokens required!"
    exit 1
fi

ssh -i $SSH_KEY $SERVER "
    sed -i 's|^FYERS_ACCESS_TOKEN=.*|FYERS_ACCESS_TOKEN=$FYERS_TOKEN|' $CONFIG_PATH
    sed -i 's|^KITE_ACCESS_TOKEN=.*|KITE_ACCESS_TOKEN=$KITE_TOKEN|' $CONFIG_PATH
"

echo "Tokens updated!"
```

---

## Useful Commands

### Check logs
```bash
ssh -i ~/.ssh/YOUR_KEY root@SERVER_IP "grep '$(date +%Y-%m-%d)' /root/bot.log | tail -50"
```

### Check if bot is running
```bash
ssh -i ~/.ssh/YOUR_KEY root@SERVER_IP "ps aux | grep vwap"
```

### View cron jobs
```bash
ssh -i ~/.ssh/YOUR_KEY root@SERVER_IP "crontab -l"
```

### Restart bot manually
```bash
ssh -i ~/.ssh/YOUR_KEY root@SERVER_IP "cd /root/ema_vwap && /root/ema_vwap/venv/bin/python vwap_ema_signal.py >> /root/bot.log 2>&1 &"
```

### Stop running bot
```bash
ssh -i ~/.ssh/YOUR_KEY root@SERVER_IP "pkill -f vwap_ema_signal.py"
```

---

## Server Requirements

| Requirement | Minimum | Recommended |
|-------------|---------|-------------|
| RAM | 512 MB | 1 GB |
| CPU | 1 vCPU | 1 vCPU |
| Disk | 5 GB | 10 GB |
| OS | Ubuntu 22.04+ | Ubuntu 24.04 |
| Network | Stable internet | Low latency |

**Cost estimate:** ~$4-6/month (DigitalOcean/AWS Lightsail)

---

## Migration Checklist

- [ ] New server created with Ubuntu 24.04
- [ ] SSH access configured
- [ ] Timezone set to Asia/Kolkata
- [ ] Python 3.12+ installed
- [ ] Virtual environment created
- [ ] Dependencies installed
- [ ] Project files copied
- [ ] config.env updated with credentials
- [ ] Cron job configured
- [ ] Test run successful
- [ ] Update update_tokens.sh with new server IP
- [ ] Update CLAUDE.md memory with new server details

---

*Last updated: April 29, 2026*
