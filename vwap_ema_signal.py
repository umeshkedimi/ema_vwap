#!/usr/bin/env python3
"""
Nifty VWAP-EMA Crossover Signal Bot
Generates buy/sell signals based on 5 EMA crossing VWAP on 5-minute candles.
Uses direct HTTP requests to Fyers API v3 (no fyers-apiv3 dependency).
"""

import os
import time
import hashlib
import logging
from datetime import datetime, timedelta

import requests
import pandas as pd
from dotenv import load_dotenv

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

load_dotenv('config.env')

FYERS_ID = os.getenv('FYERS_ID')
FYERS_APP_ID = os.getenv('FYERS_APP_ID')
FYERS_SECRET_KEY = os.getenv('FYERS_SECRET_KEY')
FYERS_REDIRECT_URI = os.getenv('FYERS_REDIRECT_URI')
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
SYMBOL = os.getenv('SYMBOL', 'NSE:NIFTY50-INDEX')
EMA_PERIOD = int(os.getenv('EMA_PERIOD', '5'))
SCAN_START_TIME = os.getenv('SCAN_START_TIME', '09:15')
SCAN_END_TIME = os.getenv('SCAN_END_TIME', '15:15')


class FyersAuth:
    """Handles authentication with Fyers API - supports manual token or browser auth."""

    def __init__(self, fyers_id, app_id, secret_key, redirect_uri):
        self.fyers_id = fyers_id
        self.app_id = app_id
        self.secret_key = secret_key
        self.redirect_uri = redirect_uri
        self.client_id = app_id

    def _generate_app_id_hash(self):
        """Generate SHA256 hash for token generation."""
        raw = f"{self.client_id}:{self.secret_key}"
        return hashlib.sha256(raw.encode()).hexdigest()

    def generate_auth_url(self):
        """Generate the authorization URL for browser login."""
        base_url = "https://api-t1.fyers.in/api/v3/generate-authcode"
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "state": "sample_state"
        }
        query_string = "&".join([f"{k}={v}" for k, v in params.items()])
        return f"{base_url}?{query_string}"

    def exchange_auth_code(self, auth_code):
        """Exchange authorization code for access token."""
        url = "https://api-t1.fyers.in/api/v3/validate-authcode"
        app_id_hash = self._generate_app_id_hash()
        payload = {
            "grant_type": "authorization_code",
            "appIdHash": app_id_hash,
            "code": auth_code
        }

        res = requests.post(url, json=payload)

        if res.status_code != 200:
            logger.error(f"Token exchange failed: {res.text}")
            raise Exception("Token exchange failed")

        response_data = res.json()
        if response_data.get("s") != "ok":
            logger.error(f"Failed to generate access token: {response_data}")
            raise Exception("Failed to generate access token")

        return response_data.get("access_token")

    def get_access_token(self):
        """Get access token - tries manual token first, then browser auth."""
        manual_token = os.getenv('FYERS_ACCESS_TOKEN')
        if manual_token:
            logger.info("Using manually provided access token")
            return manual_token

        logger.info("No access token in config. Starting browser authentication...")
        logger.info("=" * 60)

        auth_url = self.generate_auth_url()
        print("\n" + "=" * 60)
        print("FYERS AUTHENTICATION REQUIRED")
        print("=" * 60)
        print("\n1. Open this URL in your browser:\n")
        print(f"   {auth_url}\n")
        print("2. Login with your Fyers credentials (2FA required)")
        print("3. After login, you'll be redirected to a URL like:")
        print(f"   {self.redirect_uri}?auth_code=XXXXXX&state=sample_state")
        print("\n4. Copy the 'auth_code' value from that URL")
        print("=" * 60 + "\n")

        auth_code = input("Paste the auth_code here: ").strip()

        if not auth_code:
            raise Exception("No auth code provided")

        access_token = self.exchange_auth_code(auth_code)
        logger.info("Access token generated successfully")

        print("\n" + "=" * 60)
        print("TIP: To skip this tomorrow, add to config.env:")
        print(f"FYERS_ACCESS_TOKEN={access_token}")
        print("(Token is valid for one day)")
        print("=" * 60 + "\n")

        return access_token


class FyersAPI:
    """Simple Fyers API client using direct HTTP requests."""

    BASE_URL = "https://api-t1.fyers.in/api/v3"

    def __init__(self, client_id, access_token):
        self.client_id = client_id
        self.access_token = access_token
        self.headers = {
            "Authorization": f"{client_id}:{access_token}",
            "Content-Type": "application/json"
        }

    def get_profile(self):
        """Get user profile."""
        url = f"{self.BASE_URL}/profile"
        res = requests.get(url, headers=self.headers)
        return res.json()

    def history(self, data):
        """Get historical candle data."""
        url = "https://api-t1.fyers.in/data/history"
        params = {
            "symbol": data["symbol"],
            "resolution": data["resolution"],
            "date_format": data.get("date_format", "1"),
            "range_from": data["range_from"],
            "range_to": data["range_to"],
            "cont_flag": data.get("cont_flag", "1")
        }
        res = requests.get(url, headers=self.headers, params=params)
        return res.json()

    def get_quotes(self, symbols):
        """Get real-time quotes for symbols."""
        url = f"{self.BASE_URL}/quotes"
        symbol_str = ",".join(symbols) if isinstance(symbols, list) else symbols
        params = {"symbols": symbol_str}
        res = requests.get(url, headers=self.headers, params=params)
        return res.json()

    def place_order(self, order_data):
        """Place an order."""
        url = f"{self.BASE_URL}/orders/sync"
        res = requests.post(url, headers=self.headers, json=order_data)
        return res.json()


class TelegramNotifier:
    """Sends notifications via Telegram."""

    def __init__(self, bot_token, chat_id):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.base_url = f"https://api.telegram.org/bot{bot_token}"

    def send_message(self, message):
        """Send a message to the configured chat."""
        url = f"{self.base_url}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": message,
            "parse_mode": "HTML"
        }
        try:
            response = requests.post(url, json=payload, timeout=10)
            if response.status_code == 200:
                logger.info("Telegram message sent successfully")
                return True
            else:
                logger.error(f"Telegram error: {response.text}")
                return False
        except Exception as e:
            logger.error(f"Failed to send Telegram message: {e}")
            return False


class VWAPEMASignalBot:
    """Main bot that monitors Nifty and generates signals."""

    def __init__(self, fyers_client, telegram_notifier, symbol, ema_period, trade_manager=None, force_close_time="15:15"):
        self.fyers = fyers_client
        self.telegram = telegram_notifier
        self.symbol = symbol
        self.ema_period = ema_period
        self.previous_ema_above_vwap = None
        self.daily_candles = []
        self.trade_manager = trade_manager
        self.force_close_time = force_close_time

    def fetch_candles(self, days_back=5):
        """Fetch 5-minute candles from Fyers with previous days for EMA warmup."""
        today = datetime.now()
        range_from = (today - timedelta(days=days_back)).strftime("%Y-%m-%d")
        range_to = today.strftime("%Y-%m-%d")

        data = {
            "symbol": self.symbol,
            "resolution": "5",
            "date_format": "1",
            "range_from": range_from,
            "range_to": range_to,
            "cont_flag": "1"
        }

        response = self.fyers.history(data=data)

        if response.get("s") != "ok":
            logger.error(f"Failed to fetch candles: {response}")
            return None, None

        candles = response.get("candles", [])
        if not candles:
            logger.warning("No candles returned")
            return None, None

        df = pd.DataFrame(candles, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['datetime'] = pd.to_datetime(df['timestamp'], unit='s')
        df['datetime'] = df['datetime'] + pd.Timedelta(hours=5, minutes=30)
        df = df.sort_values('datetime').reset_index(drop=True)

        today_date = datetime.now().date()
        df_today = df[df['datetime'].dt.date == today_date].copy()

        return df, df_today

    def calculate_vwap(self, df):
        """Calculate VWAP for the day."""
        df = df.copy()
        df['typical_price'] = (df['high'] + df['low'] + df['close']) / 3
        df['tp_volume'] = df['typical_price'] * df['volume']
        df['cumulative_tp_volume'] = df['tp_volume'].cumsum()
        df['cumulative_volume'] = df['volume'].cumsum()
        df['vwap'] = df['cumulative_tp_volume'] / df['cumulative_volume']
        return df

    def calculate_ema(self, df_full, df_today, period):
        """Calculate EMA on full dataset (for warmup) and apply to today's data."""
        df_full = df_full.copy()
        df_today = df_today.copy()

        df_full['ema'] = df_full['close'].ewm(span=period, adjust=False).mean()

        today_indices = df_today.index.tolist()
        df_today['ema'] = df_full.loc[today_indices, 'ema'].values

        return df_today

    def check_crossover(self, df):
        """Check for EMA/VWAP crossover and return signal if detected."""
        if len(df) < 2:
            return None

        current = df.iloc[-1]
        previous = df.iloc[-2]

        current_ema = current['ema']
        current_vwap = current['vwap']
        previous_ema = previous['ema']
        previous_vwap = previous['vwap']

        current_ema_above_vwap = current_ema > current_vwap
        previous_ema_above_vwap = previous_ema > previous_vwap

        signal = None

        if not previous_ema_above_vwap and current_ema_above_vwap:
            signal = {
                'type': 'BUY',
                'price': current['close'],
                'ema': current_ema,
                'vwap': current_vwap,
                'time': current['datetime']
            }
            logger.info(f"BUY signal detected at {current['datetime']}")

        elif previous_ema_above_vwap and not current_ema_above_vwap:
            signal = {
                'type': 'SELL',
                'price': current['close'],
                'ema': current_ema,
                'vwap': current_vwap,
                'time': current['datetime']
            }
            logger.info(f"SELL signal detected at {current['datetime']}")

        return signal

    def format_signal_message(self, signal):
        """Format the signal for Telegram."""
        emoji = "🟢" if signal['type'] == 'BUY' else "🔴"
        action = "crossed above" if signal['type'] == 'BUY' else "crossed below"

        message = (
            f"{emoji} <b>{signal['type']} SIGNAL</b>\n\n"
            f"Nifty 5 EMA {action} VWAP\n\n"
            f"📊 Price: {signal['price']:.2f}\n"
            f"📈 EMA(5): {signal['ema']:.2f}\n"
            f"📉 VWAP: {signal['vwap']:.2f}\n"
            f"🕐 Time: {signal['time'].strftime('%H:%M:%S')}"
        )
        return message

    def scan_and_signal(self):
        """
        Main scan logic using historical data only.
        Waits 2 seconds after candle close for data to settle,
        then checks completed candles (index -2 vs -3) for crossover.
        """
        # Wait 2 seconds for historical data to settle
        time.sleep(2)

        logger.info("Scanning for signals (historical mode)...")

        df_full, df_today = self.fetch_candles()
        if df_full is None or df_today is None or len(df_today) < 3:
            logger.warning("Insufficient data for scanning")
            return

        df_today = self.calculate_vwap(df_today)
        df = self.calculate_ema(df_full, df_today, self.ema_period)

        # Check completed candles only (ignore the forming candle at index -1)
        # index -1: Currently forming candle (skip)
        # index -2: Just closed candle (current)
        # index -3: Previous candle (for crossover comparison)

        if len(df) < 3:
            logger.warning("Not enough candles for crossover check")
            return

        current = df.iloc[-2]   # The candle that just closed
        previous = df.iloc[-3]  # The one before it

        current_ema = current['ema']
        current_vwap = current['vwap']
        previous_ema = previous['ema']
        previous_vwap = previous['vwap']

        ema_vwap_diff = current_ema - current_vwap

        logger.info(f"Candle {current['datetime'].strftime('%H:%M')} | EMA: {current_ema:.2f} | VWAP: {current_vwap:.2f} | Diff: {ema_vwap_diff:+.2f}")

        current_ema_above_vwap = current_ema > current_vwap
        previous_ema_above_vwap = previous_ema > previous_vwap

        signal = None

        if not previous_ema_above_vwap and current_ema_above_vwap:
            signal = {
                'type': 'BUY',
                'price': current['close'],
                'ema': current_ema,
                'vwap': current_vwap,
                'time': current['datetime']
            }
            logger.info(f"BUY signal detected at {current['datetime']}")

        elif previous_ema_above_vwap and not current_ema_above_vwap:
            signal = {
                'type': 'SELL',
                'price': current['close'],
                'ema': current_ema,
                'vwap': current_vwap,
                'time': current['datetime']
            }
            logger.info(f"SELL signal detected at {current['datetime']}")

        if signal:
            message = self.format_signal_message(signal)
            self.telegram.send_message(message)

            if self.trade_manager:
                self.trade_manager.process_signal(signal)
        else:
            logger.info("No crossover detected")

    def get_next_5min_mark(self):
        """Calculate the next 5-minute candle close time."""
        now = datetime.now()
        minutes = now.minute
        next_5min = (minutes // 5 + 1) * 5

        if next_5min >= 60:
            next_time = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        else:
            next_time = now.replace(minute=next_5min, second=0, microsecond=0)

        return next_time

    def is_market_hours(self, start_time_str, end_time_str):
        """Check if current time is within market hours."""
        now = datetime.now()
        start_parts = start_time_str.split(':')
        end_parts = end_time_str.split(':')

        start_time = now.replace(hour=int(start_parts[0]), minute=int(start_parts[1]), second=0, microsecond=0)
        end_time = now.replace(hour=int(end_parts[0]), minute=int(end_parts[1]), second=0, microsecond=0)

        return start_time <= now <= end_time

    def run(self, start_time_str, end_time_str):
        """Main loop - run until market close."""
        logger.info(f"Starting signal bot for {self.symbol}")
        logger.info(f"Market hours: {start_time_str} - {end_time_str}")

        if self.trade_manager:
            mode = "PAPER" if self.trade_manager.config['paper_trading'] else "LIVE"
            trading_info = (
                f"\n\nTrading: ENABLED ({mode})\n"
                f"Max Trades: {self.trade_manager.config['max_trades_per_day']}/day\n"
                f"Target: +{self.trade_manager.config['target_points']} pts\n"
                f"SL: -{self.trade_manager.config['stoploss_points']} pts"
            )
        else:
            trading_info = "\n\nTrading: DISABLED (signals only)"

        self.telegram.send_message(
            f"🚀 <b>Signal Bot Started</b>\n\n"
            f"Symbol: {self.symbol}\n"
            f"Indicator: {self.ema_period} EMA / VWAP Crossover\n"
            f"Timeframe: 5 minutes\n"
            f"Active until: {end_time_str}"
            f"{trading_info}"
        )

        now = datetime.now()
        start_parts = start_time_str.split(':')
        market_start = now.replace(hour=int(start_parts[0]), minute=int(start_parts[1]), second=0, microsecond=0)
        first_candle_close = market_start + timedelta(minutes=5)

        if now < first_candle_close:
            wait_seconds = (first_candle_close - now).total_seconds() + 1
            logger.info(f"Waiting {wait_seconds:.0f} seconds until first candle close at {first_candle_close}")
            time.sleep(wait_seconds)

        last_status_time = datetime.now()
        fc_parts = self.force_close_time.split(':')
        force_close_time = now.replace(hour=int(fc_parts[0]), minute=int(fc_parts[1]), second=0, microsecond=0)
        last_scan_minute = -1

        while self.is_market_hours(start_time_str, end_time_str):
            now = datetime.now()

            if now >= force_close_time and self.trade_manager:
                self.trade_manager.force_close_all_positions()
                break

            if self.trade_manager and self.trade_manager.is_trading_day_complete():
                logger.info("Trading day complete - no more trades possible")
                break

            if now.minute % 5 == 0 and now.minute != last_scan_minute:
                last_scan_minute = now.minute
                self.scan_and_signal()

            if self.trade_manager:
                self.trade_manager.monitor_open_trade()

            if (now - last_status_time).total_seconds() >= 300:
                last_status_time = now
                if self.trade_manager:
                    status = self.trade_manager.get_status_message()
                    self.telegram.send_message(status)
                else:
                    self.telegram.send_message(f"Heartbeat [{now.strftime('%H:%M:%S')}] - Bot running")

            time.sleep(3)

        logger.info("Market hours ended. Shutting down.")

        if self.trade_manager:
            summary = self.trade_manager.get_daily_summary()
            self.telegram.send_message(f"🏁 <b>Session Ended</b>\n\n{summary}")
        else:
            self.telegram.send_message(
                f"🏁 <b>Signal Bot Session Ended</b>\n\n"
                f"Market hours completed for today.\n"
                f"See you tomorrow!"
            )


def main():
    """Main entry point."""
    logger.info("=" * 50)
    logger.info("Nifty VWAP-EMA Signal Bot Starting")
    logger.info("=" * 50)

    required_vars = ['FYERS_ID', 'FYERS_APP_ID', 'FYERS_SECRET_KEY',
                     'TELEGRAM_BOT_TOKEN', 'TELEGRAM_CHAT_ID']

    missing = [var for var in required_vars if not os.getenv(var)]
    if missing:
        logger.error(f"Missing required environment variables: {missing}")
        return

    try:
        auth = FyersAuth(
            fyers_id=FYERS_ID,
            app_id=FYERS_APP_ID,
            secret_key=FYERS_SECRET_KEY,
            redirect_uri=FYERS_REDIRECT_URI
        )
        access_token = auth.get_access_token()
    except Exception as e:
        logger.error(f"Authentication failed: {e}")
        return

    fyers = FyersAPI(
        client_id=FYERS_APP_ID,
        access_token=access_token
    )

    profile = fyers.get_profile()
    if profile.get("s") == "ok":
        logger.info(f"Logged in as: {profile.get('data', {}).get('name', 'Unknown')}")
    else:
        logger.warning(f"Could not fetch profile: {profile}")

    telegram = TelegramNotifier(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)

    trade_manager = None
    trading_enabled = os.getenv('TRADING_ENABLED', 'false').lower() == 'true'

    if trading_enabled:
        from kite_api import KiteAPI
        from option_selector import OptionSelector
        from trade_manager import TradeManager

        kite_api_key = os.getenv('KITE_API_KEY')
        kite_access_token = os.getenv('KITE_ACCESS_TOKEN')

        if not kite_api_key or not kite_access_token:
            logger.error("KITE_API_KEY and KITE_ACCESS_TOKEN required for trading")
            return

        kite = KiteAPI(api_key=kite_api_key, access_token=kite_access_token)
        logger.info("Kite Connect initialized for order execution")

        trading_config = {
            'paper_trading': os.getenv('PAPER_TRADING', 'true').lower() == 'true',
            'trade_start_time': os.getenv('TRADE_START_TIME', '09:30'),
            'trade_end_time': os.getenv('TRADE_END_TIME', '14:30'),
            'max_trades_per_day': int(os.getenv('MAX_TRADES_PER_DAY', '2')),
            'target_points': int(os.getenv('TARGET_POINTS', '80')),
            'stoploss_points': int(os.getenv('STOPLOSS_POINTS', '25')),
            'lot_size': int(os.getenv('LOT_SIZE', '65')),
        }

        strike_mode = os.getenv('STRIKE_MODE', 'delta')
        min_premium = int(os.getenv('MIN_PREMIUM', '220'))
        itm_offset_for_delta = int(os.getenv('ITM_OFFSET_FOR_DELTA', '150'))
        max_itm_offset = int(os.getenv('MAX_ITM_OFFSET', '300'))

        option_selector = OptionSelector(
            kite,
            strike_mode=strike_mode,
            min_premium=min_premium,
            itm_offset_for_delta=itm_offset_for_delta,
            max_itm_offset=max_itm_offset
        )

        trade_manager = TradeManager(
            kite_api=kite,
            option_selector=option_selector,
            telegram=telegram,
            config=trading_config
        )

        mode = "PAPER" if trading_config['paper_trading'] else "LIVE"
        logger.info(f"Trading ENABLED - Mode: {mode}")
    else:
        logger.info("Trading DISABLED - Signal-only mode")

    force_close_time = os.getenv('FORCE_CLOSE_TIME', '15:15')

    bot = VWAPEMASignalBot(
        fyers_client=fyers,
        telegram_notifier=telegram,
        symbol=SYMBOL,
        ema_period=EMA_PERIOD,
        trade_manager=trade_manager,
        force_close_time=force_close_time
    )

    bot.run(SCAN_START_TIME, SCAN_END_TIME)


if __name__ == "__main__":
    main()
