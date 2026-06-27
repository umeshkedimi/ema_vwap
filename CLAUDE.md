# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Nifty options trading bot that generates buy/sell signals based on 5 EMA crossing VWAP on 5-minute candles. Runs on a DigitalOcean VPS (paper-trade only; real server IP and SSH details are kept out of this public repo).

## Architecture

```
Signal Detection (Fyers API) → Trade Execution (Kite Connect API) → Notifications (Telegram)
```

**Data flow:**
1. `vwap_ema_signal.py` fetches 5-min candles from Fyers, calculates VWAP and 5 EMA
2. On crossover detection, sends Telegram alert and passes signal to `TradeManager`
3. `TradeManager` enforces trade rules (timing, max trades, target/SL)
4. `OptionSelector` picks strike based on delta (~0.7 ITM) or premium (>=220) mode
5. `KiteAPI` executes orders on Zerodha

**Key classes:**
- `VWAPEMASignalBot` (vwap_ema_signal.py) - Main bot loop, signal detection
- `TradeManager` (trade_manager.py) - Trade rules, position monitoring, P&L tracking
- `OptionSelector` (option_selector.py) - Strike selection with weekly/monthly expiry handling
- `KiteAPI` (kite_api.py) - Zerodha order execution
- `FyersAPI` (vwap_ema_signal.py) - Historical candle data

## Commands

```bash
# Run locally
source venv/bin/activate
python vwap_ema_signal.py

# Update tokens on server (run daily before 9 AM)
./update_tokens.sh

# SSH to production server (replace YOUR_SSH_KEY / YOUR_SERVER_IP with real values)
ssh -i ~/.ssh/YOUR_SSH_KEY root@YOUR_SERVER_IP

# Check today's logs on server
ssh -i ~/.ssh/YOUR_SSH_KEY root@YOUR_SERVER_IP "grep '$(date +%Y-%m-%d)' /root/bot.log | tail -100"
```

## Server Details

- **Cron:** `10 9 * * 1-5` (9:10 AM Mon-Fri)
- **Log file:** `/root/bot.log`
- **Config:** `/root/ema_vwap/config.env`

## Trade Rules (v2.0 - Trailing SL)

**Entry:**
- No trades before 9:30 AM or after 2:30 PM (the 10:00 start filter was removed Jun 27 — post-implementation tally showed it blocked more would-be winners than losers it avoided; see LEARNINGS.md §7b)
- One open position at a time
- MAX_TRADES_PER_DAY=1

**Exit (Trailing SL):**
- Initial SL: -25 pts from entry
- At +50 pts: SL moves to breakeven (entry price)
- At +75 pts: SL moves to +50 (locks 50 pts)
- Trails every 5 pts thereafter, always 25 pts behind (+80 → SL +55, +85 → SL +60, +100 → SL +75, etc.)
- No fixed target - winners run until trailing SL hit
- Force close at 3:15 PM

**One-Trade Rule (since Jun 27):**
- MAX_TRADES_PER_DAY=1 — the trading day ends after the first trade closes, win or lose.
- (Previously 2 trades with a "first-trade-profit → no second trade" rule; simplified to a single trade per day.)

**Philosophy:** Cut losses early (-25), let winners run. Inspired by Tom Hougaard's "Best Loser Wins".

## Daily Workflow with User

1. User says "pull the logs" after market hours
2. Pull logs: `ssh ... "grep '$(date +%Y-%m-%d)' /root/bot.log"`
3. Logs show actual fill prices (entry/exit updated lines)
4. Summarize trades and update `trade_journal.csv`
5. **(Retired Jun 27)** Pre-10:00 blocked-signal tracking — no longer applies now that
   `TRADE_START_TIME=09:30`. Signals in 09:30–10:00 now execute normally instead of
   being skipped, so there are no "Outside trading hours" blocks to log. The historical
   tally lives in `skipped_premarket_signals.csv` + LEARNINGS.md §7b; leave it as a record.
6. Sync journal to server. **Do NOT push to GitHub** unless the user explicitly says so
   (commit locally + sync to server only — see memory `no-auto-push`).

## Key Technical Decisions

- **Actual fills:** Bot uses real Kite fill prices, not LTP. See `get_fill_price()` in `kite_api.py`
- **Force close:** Runs AFTER main loop exits (not inside loop) to guarantee execution
- **Config:** `config.env` stays on server only (has credentials). `config.example.env` is in git

## New Machine Setup

When setting up on a new laptop:

1. **Clone the repo:**
   ```bash
   git clone git@github.com:umeshkedimi/ema_vwap.git
   cd ema_vwap
   ```

2. **Copy SSH key from old laptop:**
   ```bash
   # On old laptop, copy to new (use your actual key filename)
   scp ~/.ssh/YOUR_SSH_KEY user@new-laptop:~/.ssh/
   scp ~/.ssh/YOUR_SSH_KEY.pub user@new-laptop:~/.ssh/
   
   # Or generate new key and add to server
   ssh-keygen -t ed25519 -f ~/.ssh/YOUR_SSH_KEY
   # Then add public key to server's ~/.ssh/authorized_keys
   ```

3. **Install Claude Code and start:**
   ```bash
   npm install -g @anthropic-ai/claude-code
   claude
   ```

Claude reads `CLAUDE.md` automatically - all context is preserved.

## Option Symbol Formats

Weekly: `NIFTY{YY}{M}{DD}{strike}{CE/PE}` - e.g., `NIFTY2642124500CE` (Apr 21, 2026)
Monthly: `NIFTY{YY}{MON}{strike}{CE/PE}` - e.g., `NIFTY26APR24500CE` (last Tuesday of month)

Month codes for weekly: 1-9 for Jan-Sep, O/N/D for Oct/Nov/Dec

## API Notes

- **Fyers:** Uses v3 API with direct HTTP requests (no SDK). Tokens valid 1 day.
- **Kite:** Uses v3 API. MARKET orders require `market_protection` parameter via API.
- Expiry is Tuesday (weekly), not Thursday.
