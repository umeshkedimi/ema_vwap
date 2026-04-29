# Trading Bot Learnings

Documentation of key learnings from building and running the VWAP-EMA signal bot.

---

## 1. API & Execution

### Kite Connect
- **Market protection required**: MARKET orders via API require `market_protection` parameter (set to 2 for 2% cap)
- Without it, orders get rejected with: "Market orders without market protection are not allowed via API"

### Fyers API
- Returns **currently forming candle** in historical data (not just completed ones)
- Data available within 2 seconds of candle close
- Tokens expire daily - must update before 9 AM

### Slippage
- Entry slippage: 1-3 points typical
- Exit slippage on SL: 5+ points (fast moves, market orders)
- Budget for ~3-5 points slippage per trade

---

## 2. Strike Selection

### Problem (Apr 27)
- Old logic used ATM as base, rounded to nearest 50
- Nifty 24,046 → ATM 24,050 → Strike 23,900 CE (only 146 pts ITM)
- Lower delta (~0.65) → option moved only +40 pts
- Breakeven trigger (+50 pts) missed → SL hit → Loss

### Fix
- Use spot price as base, round DOWN for CE / UP for PE
- Nifty 24,046 → floor((24046-150)/50)*50 = 23,850 CE (196 pts ITM)
- Higher delta (~0.75) → option moves faster
- Breakeven trigger more likely to hit

### Code Change (option_selector.py)
```python
# CE: round DOWN to ensure minimum ITM
itm_strike = math.floor((nifty_price - self.itm_offset_for_delta) / 50) * 50

# PE: round UP to ensure minimum ITM  
itm_strike = math.ceil((nifty_price + self.itm_offset_for_delta) / 50) * 50
```

---

## 3. Signal Detection

### Problem (Apr 29)
- Real-time scan missed thin crossovers (09:40 BUY +5.73 pts, 14:15 SELL -3.15 pts)
- Real-time scan detected false positive (14:45 BUY +1.17 pts - not confirmed by historical)
- Historical data (review_signals.py) showed the TRUE signals clearly
- Root cause: Real-time data includes noise; checking forming candle is unreliable

### Fix: Historical-Only Scanning (Final Solution)
- **Removed real-time scan entirely**
- Wait 2 seconds after candle close for data to settle
- Check ONLY completed candles (index -2 vs -3)
- Matches exactly what review_signals.py shows

### Why Historical is Better
| Scan Type | 09:40 BUY | 14:15 SELL | 14:45 "BUY" |
|-----------|-----------|------------|-------------|
| Real-time | ❌ Missed | ❌ Missed | ❌ False positive |
| Historical | ✅ Found | ✅ Found | ✅ Correctly ignored |

### Code Change (vwap_ema_signal.py)
```python
def scan_and_signal(self):
    # Wait 2 seconds for historical data to settle
    time.sleep(2)
    
    # Fetch historical data
    df_full, df_today = self.fetch_candles()
    
    # Check COMPLETED candles only (ignore forming candle at index -1)
    current = df.iloc[-2]   # Just closed
    previous = df.iloc[-3]  # Previous
    
    # Crossover check on settled data
    if not prev_above and curr_above:
        signal = BUY
    elif prev_above and not curr_above:
        signal = SELL
```

### Candle Indexing
```
At 09:40:02:
  df.iloc[-1] = 09:40 candle (FORMING - ignored)
  df.iloc[-2] = 09:35 candle (JUST CLOSED - current)
  df.iloc[-3] = 09:30 candle (previous - for comparison)
```

---

## 4. Risk Management Rules

| Rule | Implementation |
|------|----------------|
| Max 1 trade/day | `MAX_TRADES_PER_DAY=1` in config |
| No trades before 9:30 AM | `TRADE_START_TIME=09:30` |
| No trades after 2:30 PM | `TRADE_END_TIME=14:30` |
| Force close at 3:15 PM | `FORCE_CLOSE_TIME=15:15` |
| Target: +80 points | `TARGET_POINTS=80` |
| Stop loss: -25 points | `STOPLOSS_POINTS=25` |
| Breakeven at +50 pts | SL moves to entry when +50 in favor |

---

## 5. Option Symbol Formats

### Weekly Expiry
```
NIFTY{YY}{M}{DD}{strike}{CE/PE}
Example: NIFTY2642124500CE (Apr 21, 2026)
Month codes: 1-9 for Jan-Sep, O/N/D for Oct/Nov/Dec
```

### Monthly Expiry (last Tuesday of month)
```
NIFTY{YY}{MON}{strike}{CE/PE}
Example: NIFTY26APR24500CE
```

### Expiry Day
- Tuesday (not Thursday like before)

---

## 6. Operational Learnings

### Daily Routine
1. Update tokens before 9 AM: `./update_tokens.sh`
2. Bot runs automatically at 9:10 AM (cron)
3. Check logs if needed: `ssh ... "grep '$(date +%Y-%m-%d)' /root/bot.log"`

### Debugging
- Always check actual fills vs logged prices (slippage)
- Use `review_signals.py` to analyze signals after market hours
- Compare real-time vs historical data when signals are missed

### What NOT to Change
- Don't migrate to FastAPI if current setup works
- Don't add complexity for marginal gains
- Real money = stability over features

---

## 7. Trade Journal

See `trade_journal.csv` for actual trade records with:
- Date, signal, option, strike
- Entry/exit (logged vs actual)
- Result, P&L, notes

---

## 8. Key Files

| File | Purpose |
|------|---------|
| `vwap_ema_signal.py` | Main bot - signal detection, confirmation scan |
| `trade_manager.py` | Trade rules, breakeven logic, P&L tracking |
| `option_selector.py` | Strike selection (delta/premium mode) |
| `kite_api.py` | Order execution (Zerodha) |
| `review_signals.py` | Post-market signal analysis |
| `config.env` | All configuration parameters |
| `trade_journal.csv` | Trade records |

---

## 9. Timeline of Changes

| Date | Change | Reason |
|------|--------|--------|
| Apr 21 | Added `market_protection=2` to Kite orders | Order rejection fix |
| Apr 24 | Changed `MAX_TRADES_PER_DAY` to 1 | Risk management |
| Apr 24 | Added breakeven SL at +50 pts | Protect profits |
| Apr 27 | Fixed strike selection (floor/ceil) | Higher delta for breakeven |
| Apr 29 | Switched to historical-only scanning (2 sec delay) | Catch thin crossovers, avoid false positives |

---

## 10. Performance Summary

| Trade | Date | Option | Result | P&L |
|-------|------|--------|--------|-----|
| 1 | Apr 27 | 23900 CE | SL Hit | -₹1,985.75 |
| 2 | Apr 28 | 24350 PE | Target | +₹5,034.25 |
| **Net** | | | | **+₹3,048.50** |

*Updated: April 29, 2026*
