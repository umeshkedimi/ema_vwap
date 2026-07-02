# Nifty VWAP-EMA Signal Bot

Automated trading bot for Nifty options based on 5 EMA crossing VWAP on 5-minute candles.

## Strategy

**Entry Signal:**
- **BUY**: When 5 EMA crosses above VWAP → Buy CE (Call) option
- **SELL**: When 5 EMA crosses below VWAP → Buy PE (Put) option

**Exit Rules (Trailing SL):**
- **Stop Loss**: -25 points from entry
- **Breakeven**: At +50 pts, SL moves to entry (0)
- **Trailing SL**: At +75 pts, SL moves to +50, then trails every 5 pts (always 25 behind)
- **No fixed target**: Winners run until trailing SL is hit
- **Force Close**: 3:15 PM if still open

```
SL Progression:
Entry → SL at -25
+50 pts → SL moves to 0 (breakeven)
+75 pts → SL moves to +50 (lock 50)
+80 pts → SL moves to +55 (lock 55)
+85 pts → SL moves to +60 (lock 60)
+100 pts → SL moves to +75 (lock 75)
... trails every 5 pts, always 25 behind
```

**Philosophy**: Cut losses early (-25), let winners run (trailing SL). Inspired by Tom Hougaard's "Best Loser Wins".

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

## Key Findings

Findings from running the bot live (paper) and backtesting the trade log. Full detail in [`LEARNINGS.md`](LEARNINGS.md).

**The system is asymmetric by design, not by accident.** Across 32 logged trades the win rate is ~25% (8W/24L), but the average win (+83.5 pts) is ~3.5× the average loss (−23.6 pts), giving a positive expectancy of ~+3.2 pts/trade. Frequent small stop-losses punctuated by rare large runners is the *intended* texture — a cluster of SL hits is normal, not a malfunction.

**Crossover strength has no predictive edge — so I didn't add a filter for it.** It was tempting to filter out "thin" EMA/VWAP crossovers after a losing streak, but the data refuted it: correlation between crossover separation and outcome was −0.03, and the three *widest* crossovers in the sample all lost. Threshold sweeps swung wildly on the small sample (classic overfitting), so the filter was rejected.

**The one real edge is time of day.** Entries before 10:00 AM were the money pit (−157 pts over 13 trades) — VWAP is still forming on the opening candles, making the early crossover unreliable. Blocking entries before 10:00 lifts net performance from +101 → +258 pts at the cost of only two small winners. This became the single data-supported change (`TRADE_START_TIME=10:00`).

**Points-positive but rupees-negative pointed to position sizing as the bigger lever.** The sample was +101 pts yet −₹23k, because size was largest during a drawdown. The signal wasn't the main problem — risk sizing was.

> **Caveat:** 32 trades / 8 wins is a small sample, so these splits may be partly regime-driven. The takeaway is the *process* — test the hypothesis against the full log, reject what overfits, and change only what the data supports.

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
MAX_TRADES_PER_DAY=2    # Max 2 trades per day
STOPLOSS_POINTS=25      # Initial SL at -25 points
LOT_SIZE=130            # Quantity (1 lot = 65)

# Strike selection
STRIKE_MODE=delta       # delta or premium
MIN_PREMIUM=220         # Minimum option premium
ITM_OFFSET_FOR_DELTA=150  # ITM points for delta mode
```

## Trade Rules

1. **Timing**: No trades before 9:30 AM or after 2:30 PM
2. **One at a time**: Must close current trade before taking next signal
3. **Daily limit**: Max 2 trades per day
4. **Pre-10 AM block**: Only 1 trade allowed before 10:00 AM — if Trade 1 opens and closes before 10:00, Trade 2 must wait until after 10:00 AM
5. **Second trade condition**: Trade 2 only fires if Trade 1 closed with SL hit or breakeven — if Trade 1 exits in profit, day ends
6. **Expiry**: Weekly options (Tuesday expiry)

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

Fyers and Kite tokens expire daily. First-time setup — copy the template and fill in
your server IP and SSH key (the real `update_tokens.sh` is gitignored so credentials
stay private):

```bash
cp update_tokens.example.sh update_tokens.sh
# edit SERVER and SSH_KEY at the top, then:
./update_tokens.sh
```

Or manually update `FYERS_ACCESS_TOKEN` and `KITE_ACCESS_TOKEN` in config.env.

## Telegram Notifications

The bot sends alerts for:
- Bot startup and token validation
- Every candle scan (EMA/VWAP values)
- Signal detection
- Trade entry with option details
- Breakeven trigger (+50 pts)
- Trailing SL updates (+75, +80, +85... every 5 pts)
- Trade exit (trailing SL/SL/breakeven)
- Daily summary

## Version History

### v2.1 (July 2026) - Two Trades
- MAX_TRADES_PER_DAY raised to 2 (LOT_SIZE=130, 2 lots × 65)
- Trade 2 only if Trade 1 closed with SL hit or breakeven (profit → day ends)
- Pre-10 AM block: max 1 trade before 10:00 AM

### v2.0 (June 2026) - Trailing SL
- Replaced fixed +80 target with trailing SL starting at +75
- Philosophy: Cut losses early, let winners run

### v1.0 (April 2026) - Initial Release
- Fixed target +80, SL -25, breakeven at +50
- 1 trade per day
- Delta mode strike selection

## Disclaimer

This bot is for educational purposes. Trading involves risk. Past performance does not guarantee future results. Use at your own risk.
