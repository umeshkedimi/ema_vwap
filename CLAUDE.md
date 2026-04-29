# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Nifty options trading bot that generates buy/sell signals based on 5 EMA crossing VWAP on 5-minute candles. Runs on a DigitalOcean VPS at `64.227.163.187`.

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

# SSH to production server
ssh -i ~/.ssh/id_ed25519_ai_dev root@64.227.163.187

# Check today's logs on server
ssh -i ~/.ssh/id_ed25519_ai_dev root@64.227.163.187 "grep '$(date +%Y-%m-%d)' /root/bot.log | tail -100"
```

## Server Details

- **Cron:** `10 9 * * 1-5` (9:10 AM Mon-Fri)
- **Log file:** `/root/bot.log`
- **Config:** `/root/ema_vwap/config.env`

## Trade Rules (enforced in TradeManager)

- No trades before 9:30 AM or after 2:30 PM
- Max trades per day configured in `MAX_TRADES_PER_DAY`
- If first trade hits target → no more trades that day
- One open position at a time
- Force close at 3:15 PM

## Option Symbol Formats

Weekly: `NIFTY{YY}{M}{DD}{strike}{CE/PE}` - e.g., `NIFTY2642124500CE` (Apr 21, 2026)
Monthly: `NIFTY{YY}{MON}{strike}{CE/PE}` - e.g., `NIFTY26APR24500CE` (last Tuesday of month)

Month codes for weekly: 1-9 for Jan-Sep, O/N/D for Oct/Nov/Dec

## API Notes

- **Fyers:** Uses v3 API with direct HTTP requests (no SDK). Tokens valid 1 day.
- **Kite:** Uses v3 API. MARKET orders require `market_protection` parameter via API.
- Expiry is Tuesday (weekly), not Thursday.
