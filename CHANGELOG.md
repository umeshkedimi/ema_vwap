# Changelog

All notable changes to the Nifty VWAP-EMA Trading Bot.

## [2.1.0] - 2026-06-05

### Changed
- **Lot size**: 2 lots (130) → 3 lots (195) after 3 profitable days

## [2.0.1] - 2026-06-04

### Fixed
- **Force close bug**: Position wasn't closing at 3:15 PM because force close logic was inside the while loop which exited before it could run. Moved force close to run AFTER loop exits.
- **Actual fill prices**: Entry and exit now use real fill prices from Kite API instead of LTP. Added `get_fill_price()` method that polls order history until filled. All calculations (SL, trailing, P&L) and Telegram notifications now show actual fills.

### Changed
- **Telegram messages**: Removed outdated "Target: +80 pts" from startup. Status now shows trailing levels instead of fixed target.

## [2.0.0] - 2026-06-03

### Changed
- **Trailing SL system**: Replaced fixed +80 target with trailing stop loss
  - SL starts at -25 from entry
  - At +50 pts: SL moves to breakeven (entry price)
  - At +75 pts: SL moves to +50 (locks 50 pts profit)
  - Continues trailing every 25 pts (+100 → SL at +75, etc.)
  - No fixed target - winners run until trailing SL is hit
- **2 trades per day**: Changed MAX_TRADES_PER_DAY from 1 to 2
  - If first trade exits with profit → no second trade
  - If first trade hits SL or breakeven → second trade allowed
- **Philosophy**: Cut losses early (-25), let winners run. Inspired by Tom Hougaard's "Best Loser Wins"

## [1.0.0] - 2026-04

### Initial Release
- VWAP-EMA crossover strategy on 5-minute Nifty candles
- Fixed target: +80 points
- Fixed stop loss: -25 points
- Breakeven at +50 points
- 1 trade per day max
- Delta mode strike selection (~0.7 ITM)
- Fyers API for signals, Kite Connect for orders, Telegram for alerts
