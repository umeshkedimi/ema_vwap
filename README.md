# Nifty VWAP-EMA Signal Bot

Automated trading bot for Nifty options based on 5 EMA crossing VWAP on 5-minute candles.

## Strategy

**Entry Signal:**
- **BUY**: When 5 EMA crosses above VWAP → Buy CE (Call) option
- **SELL**: When 5 EMA crosses below VWAP → Buy PE (Put) option

**Exit Rules:**
- **Target**: +80 points from entry
- **Stop Loss**: -25 points from entry
- **Breakeven**: When trade reaches +50 points, SL moves to entry price
- **Force Close**: 3:15 PM if still open

**Risk/Reward**: 3.2:1 (need only ~24% win rate to break even)

## Architecture

```
Fyers API (Candles) → Signal Detection → Kite API (Orders) → Telegram (Alerts)
```

| Component | Purpose |
|-----------|---------|
| `vwap_ema_signal.py` | Main bot - fetches candles, calculates indicators, detects signals |
| `trade_manager.py` | Enforces trade rules, monitors positions, tracks P&L |
| `option_selector.py` | Selects strike based on delta (~0.7 ITM) or premium mode |
| `kite_api.py` | Zerodha order execution |

## Setup

### 1. Clone and configure

```bash
git clone git@github.com:umeshkedimi/ema_vwap.git
cd ema_vwap
cp config.example.env config.env
# Edit config.env with your API credentials
```

### 2. Install dependencies

```bash
python3 -m venv venv
source venv/bin/activate
pip install requests pandas numpy
```

### 3. API Credentials Required

| API | Purpose | Get from |
|-----|---------|----------|
| Fyers | Historical candle data | [Fyers API](https://myapi.fyers.in/) |
| Kite Connect | Order execution | [Kite Connect](https://kite.trade/) |
| Telegram | Trade alerts | [@BotFather](https://t.me/botfather) |

### 4. Run locally

```bash
source venv/bin/activate
python vwap_ema_signal.py
```

### 5. Server deployment (optional)

See `SERVER_SETUP.md` for DigitalOcean VPS setup and cron configuration.

## Configuration

Edit `config.env`:

```env
# Trading mode
TRADING_ENABLED=true    # Enable/disable order execution
PAPER_TRADING=false     # true = simulate orders, false = live trading

# Trade timing
TRADE_START_TIME=09:30  # No trades before this (skip first 15 min)
TRADE_END_TIME=14:30    # No trades after this

# Trade parameters
MAX_TRADES_PER_DAY=1    # Maximum trades per day
TARGET_POINTS=80        # Exit at +80 points
STOPLOSS_POINTS=25      # Exit at -25 points
LOT_SIZE=325            # Quantity (1 lot = 65)

# Strike selection
STRIKE_MODE=delta       # delta or premium
MIN_PREMIUM=220         # Minimum option premium
ITM_OFFSET_FOR_DELTA=150  # ITM points for delta mode
```

## Trade Rules

1. **Timing**: No trades before 9:30 AM or after 2:30 PM
2. **One at a time**: Must close current trade before taking next signal
3. **Daily limit**: Configurable max trades per day
4. **Target rule**: If first trade hits target, no more trades that day
5. **Expiry**: Weekly options (Tuesday expiry)

## Option Symbol Formats

```
Weekly:  NIFTY{YY}{M}{DD}{strike}{CE/PE}  → NIFTY2651923600CE (May 19, 2026)
Monthly: NIFTY{YY}{MON}{strike}{CE/PE}   → NIFTY26MAY23600CE

Month codes (weekly): 1-9 for Jan-Sep, O/N/D for Oct/Nov/Dec
```

## Files

```
ema_vwap/
├── vwap_ema_signal.py   # Main bot
├── trade_manager.py     # Trade rules & execution
├── option_selector.py   # Strike selection
├── kite_api.py          # Zerodha API client
├── review_signals.py    # Backtest/review tool
├── config.env           # Your credentials (not in git)
├── config.example.env   # Template config
├── trade_journal.csv    # Trade history with actual fills
└── SERVER_SETUP.md      # Deployment guide
```

## Daily Token Update

Fyers and Kite tokens expire daily. Update before 9:10 AM:

```bash
./update_tokens.sh
```

Or manually update `FYERS_ACCESS_TOKEN` and `KITE_ACCESS_TOKEN` in config.env.

## Telegram Notifications

The bot sends alerts for:
- Bot startup and token validation
- Every candle scan (EMA/VWAP values)
- Signal detection
- Trade entry with option details
- Breakeven trigger
- Trade exit (target/SL/breakeven)
- Daily summary

## Disclaimer

This bot is for educational purposes. Trading involves risk. Past performance does not guarantee future results. Use at your own risk.
