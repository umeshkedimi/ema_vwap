#!/usr/bin/env python3
"""
Review signals generated for a trading day.
Run after market hours to see all EMA/VWAP crossovers that occurred.
"""

import os
import sys
from datetime import datetime, timedelta

import requests
import pandas as pd
from dotenv import load_dotenv

load_dotenv('config.env')

FYERS_APP_ID = os.getenv('FYERS_APP_ID')
FYERS_ACCESS_TOKEN = os.getenv('FYERS_ACCESS_TOKEN')
SYMBOL = os.getenv('SYMBOL', 'NSE:NIFTY50-INDEX')
EMA_PERIOD = int(os.getenv('EMA_PERIOD', '5'))


def fetch_candles(date_str=None, include_prev_day=True):
    """Fetch 5-minute candles for a given date, optionally with previous day for EMA warmup."""
    if date_str:
        target_date = datetime.strptime(date_str, '%Y-%m-%d')
    else:
        target_date = datetime.now()

    headers = {
        "Authorization": f"{FYERS_APP_ID}:{FYERS_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }

    if include_prev_day:
        range_from = (target_date - timedelta(days=5)).strftime('%Y-%m-%d')
    else:
        range_from = target_date.strftime('%Y-%m-%d')
    range_to = (target_date + timedelta(days=1)).strftime('%Y-%m-%d')

    params = {
        "symbol": SYMBOL,
        "resolution": "5",
        "date_format": "1",
        "range_from": range_from,
        "range_to": range_to,
        "cont_flag": "1"
    }

    url = "https://api-t1.fyers.in/data/history"
    response = requests.get(url, headers=headers, params=params)
    result = response.json()

    if result.get("s") != "ok":
        print(f"Error fetching data: {result}")
        return None, None

    candles = result.get("candles", [])
    if not candles:
        print("No candles returned for this date")
        return None, None

    df = pd.DataFrame(candles, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['datetime'] = pd.to_datetime(df['timestamp'], unit='s')
    df['datetime'] = df['datetime'] + pd.Timedelta(hours=5, minutes=30)
    df = df.sort_values('datetime').reset_index(drop=True)

    df_target = df[df['datetime'].dt.date == target_date.date()].copy()

    return df, df_target


def calculate_indicators(df_full, df_target):
    """Calculate VWAP (daily reset) and EMA (continuous from previous days)."""
    df_full = df_full.copy()
    df_target = df_target.copy()

    df_full['ema'] = df_full['close'].ewm(span=EMA_PERIOD, adjust=False).mean()

    target_indices = df_target.index.tolist()
    df_target['ema'] = df_full.loc[target_indices, 'ema'].values

    df_target['typical_price'] = (df_target['high'] + df_target['low'] + df_target['close']) / 3
    df_target['tp_volume'] = df_target['typical_price'] * df_target['volume']
    df_target['cumulative_tp_volume'] = df_target['tp_volume'].cumsum()
    df_target['cumulative_volume'] = df_target['volume'].cumsum()
    df_target['vwap'] = df_target['cumulative_tp_volume'] / df_target['cumulative_volume']

    df_target['ema_above_vwap'] = df_target['ema'] > df_target['vwap']

    return df_target


def detect_signals(df):
    """Detect all crossover signals."""
    signals = []

    for i in range(1, len(df)):
        prev = df.iloc[i - 1]
        curr = df.iloc[i]

        prev_above = prev['ema_above_vwap']
        curr_above = curr['ema_above_vwap']

        if not prev_above and curr_above:
            signals.append({
                'type': 'BUY',
                'time': curr['datetime'],
                'price': curr['close'],
                'ema': curr['ema'],
                'vwap': curr['vwap']
            })
        elif prev_above and not curr_above:
            signals.append({
                'type': 'SELL',
                'time': curr['datetime'],
                'price': curr['close'],
                'ema': curr['ema'],
                'vwap': curr['vwap']
            })

    return signals


def print_report(df, signals, date_str):
    """Print the daily report."""
    print("=" * 70)
    print(f"  NIFTY 50 - EMA/VWAP CROSSOVER SIGNALS - {date_str}")
    print("=" * 70)

    if df is not None and len(df) > 0:
        print(f"\nMarket Data Summary:")
        print(f"  Candles Analyzed : {len(df)}")
        print(f"  First Candle     : {df.iloc[0]['datetime'].strftime('%H:%M')} - Open: {df.iloc[0]['open']:.2f}")
        print(f"  Last Candle      : {df.iloc[-1]['datetime'].strftime('%H:%M')} - Close: {df.iloc[-1]['close']:.2f}")
        print(f"  Day High         : {df['high'].max():.2f}")
        print(f"  Day Low          : {df['low'].min():.2f}")
        print(f"  Final VWAP       : {df.iloc[-1]['vwap']:.2f}")
        print(f"  Final EMA({EMA_PERIOD})     : {df.iloc[-1]['ema']:.2f}")

    print("\n" + "-" * 70)
    print(f"  SIGNALS GENERATED: {len(signals)}")
    print("-" * 70)

    if not signals:
        print("\n  No crossover signals were generated today.")
    else:
        for i, signal in enumerate(signals, 1):
            emoji = "BUY " if signal['type'] == 'BUY' else "SELL"
            print(f"\n  [{i}] {emoji} at {signal['time'].strftime('%H:%M:%S')}")
            print(f"      Price: {signal['price']:.2f}")
            print(f"      EMA({EMA_PERIOD}): {signal['ema']:.2f}")
            print(f"      VWAP:  {signal['vwap']:.2f}")
            diff = signal['ema'] - signal['vwap']
            print(f"      EMA-VWAP Diff: {diff:+.2f}")

    print("\n" + "=" * 70)

    if signals:
        print("\nSignal Timeline:")
        print("-" * 40)
        for signal in signals:
            arrow = "^" if signal['type'] == 'BUY' else "v"
            print(f"  {signal['time'].strftime('%H:%M')} {arrow} {signal['type']:4} @ {signal['price']:.2f}")
        print("-" * 40)


def main():
    if not FYERS_APP_ID or not FYERS_ACCESS_TOKEN:
        print("ERROR: FYERS_APP_ID and FYERS_ACCESS_TOKEN must be set in config.env")
        return

    if len(sys.argv) > 1:
        date_str = sys.argv[1]
        try:
            datetime.strptime(date_str, '%Y-%m-%d')
        except ValueError:
            print("Invalid date format. Use: YYYY-MM-DD")
            print("Example: python3 review_signals.py 2026-04-18")
            return
    else:
        date_str = datetime.now().strftime('%Y-%m-%d')

    print(f"\nFetching data for {date_str} (with previous days for EMA warmup)...")

    df_full, df_target = fetch_candles(date_str)

    if df_full is None or df_target is None or df_target.empty:
        print(f"No data available for {date_str}")
        print("Note: Data is only available for trading days (Mon-Fri, excluding holidays)")
        return

    df = calculate_indicators(df_full, df_target)
    signals = detect_signals(df)
    print_report(df, signals, date_str)


if __name__ == "__main__":
    main()
