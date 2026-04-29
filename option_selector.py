#!/usr/bin/env python3
"""
Option Strike Selection for Nifty Options Trading.
Supports two modes:
  - delta: Target delta ~0.7 (faster profits)
  - premium: Target premium >= 220 (liquidity focus)
Uses Kite Connect API for quotes.
"""

import logging
import math
from datetime import datetime, date, timedelta
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class OptionContract:
    """Represents a selected option contract."""
    tradingsymbol: str
    exchange: str
    strike: int
    option_type: str
    expiry: date
    premium: float


class OptionSelector:
    """Selects appropriate option strikes based on signal and configuration."""

    def __init__(self, kite_api, strike_mode: str = "delta", min_premium: int = 220,
                 itm_offset_for_delta: int = 150, max_itm_offset: int = 300):
        """
        Args:
            kite_api: Kite API client
            strike_mode: "delta" or "premium"
            min_premium: Minimum premium required (both modes)
            itm_offset_for_delta: ITM offset for delta ~0.7 (delta mode only)
            max_itm_offset: Maximum ITM offset to search
        """
        self.kite = kite_api
        self.strike_mode = strike_mode.lower()
        self.min_premium = min_premium
        self.itm_offset_for_delta = itm_offset_for_delta
        self.max_itm_offset = max_itm_offset

        logger.info(f"Strike mode: {self.strike_mode.upper()}")

    def get_current_expiry(self) -> date:
        """
        Get current week's expiry (Tuesday).
        If today is Tuesday after 3:30 PM or any day after Tuesday, return next Tuesday.
        """
        today = date.today()
        current_weekday = today.weekday()

        days_until_tuesday = (1 - current_weekday) % 7

        if days_until_tuesday == 0:
            now = datetime.now()
            if now.hour >= 16:
                days_until_tuesday = 7
        elif current_weekday > 1:
            days_until_tuesday = (8 - current_weekday) % 7
            if days_until_tuesday == 0:
                days_until_tuesday = 7

        expiry = today + timedelta(days=days_until_tuesday)
        logger.info(f"Next expiry: {expiry} (today: {today}, weekday: {current_weekday})")
        return expiry

    def is_monthly_expiry(self, expiry: date) -> bool:
        """Check if this Tuesday is the last Tuesday of the month (monthly expiry)."""
        next_tuesday = expiry + timedelta(days=7)
        return next_tuesday.month != expiry.month

    def build_tradingsymbol(self, strike: int, option_type: str, expiry: date) -> str:
        """
        Build Kite tradingsymbol for NFO options.

        Monthly expiry (last Tuesday of month):
            Format: NIFTY{YY}{MON}{strike}{CE/PE}
            Example: NIFTY26APR24500CE

        Weekly expiry:
            Format: NIFTY{YY}{M}{DD}{strike}{CE/PE}
            Month codes: 1-9 for Jan-Sep, O/N/D for Oct/Nov/Dec
            Example: NIFTY2642124500CE (Apr 21, 2026)
        """
        year_code = str(expiry.year)[-2:]

        if self.is_monthly_expiry(expiry):
            month_names = ['', 'JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN',
                          'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC']
            month_code = month_names[expiry.month]
            symbol = f"NIFTY{year_code}{month_code}{strike}{option_type}"
            logger.info(f"Monthly expiry symbol: {symbol}")
            return symbol
        else:
            month = expiry.month
            if month <= 9:
                month_code = str(month)
            elif month == 10:
                month_code = 'O'
            elif month == 11:
                month_code = 'N'
            else:
                month_code = 'D'

            day_code = f"{expiry.day:02d}"
            symbol = f"NIFTY{year_code}{month_code}{day_code}{strike}{option_type}"
            logger.info(f"Weekly expiry symbol: {symbol}")
            return symbol

    def get_atm_strike(self, nifty_price: float) -> int:
        """Get ATM strike (rounded to nearest 50)."""
        return round(nifty_price / 50) * 50

    def get_option_premium(self, tradingsymbol: str) -> Optional[float]:
        """Fetch current premium (LTP) for an option using Kite API."""
        try:
            symbol_with_exchange = f"NFO:{tradingsymbol}"
            result = self.kite.get_ltp([symbol_with_exchange])

            if result and symbol_with_exchange in result:
                return result[symbol_with_exchange].get('last_price')
            else:
                logger.warning(f"Could not get quote for {tradingsymbol}: {result}")
                return None
        except Exception as e:
            logger.error(f"Error fetching quote for {tradingsymbol}: {e}")
            return None

    def select_strike(self, nifty_price: float, signal_type: str) -> Optional[OptionContract]:
        """
        Select strike based on configured mode.

        DELTA mode (strike_mode='delta'):
            - Start with ITM strike (150 points ITM for delta ~0.7)
            - Ensure premium >= 220
            - Faster profit capture

        PREMIUM mode (strike_mode='premium'):
            - Start with ATM strike
            - Move ITM until premium >= 220
            - Better liquidity focus
        """
        if self.strike_mode == "delta":
            return self._select_strike_delta_mode(nifty_price, signal_type)
        else:
            return self._select_strike_premium_mode(nifty_price, signal_type)

    def _select_strike_delta_mode(self, nifty_price: float, signal_type: str) -> Optional[OptionContract]:
        """
        DELTA MODE: Target delta ~0.7 for faster profits.

        Logic:
        - Start with ITM strike (150 points ITM)
        - If premium >= 220, use it
        - If premium < 220, go deeper ITM until premium >= 220
        """
        option_type = 'CE' if signal_type == 'BUY' else 'PE'
        expiry = self.get_current_expiry()

        # Calculate ITM strike ensuring minimum ITM offset from spot price
        if option_type == 'CE':
            # CE: strike below spot, round DOWN to ensure minimum ITM
            itm_strike = math.floor((nifty_price - self.itm_offset_for_delta) / 50) * 50
        else:
            # PE: strike above spot, round UP to ensure minimum ITM
            itm_strike = math.ceil((nifty_price + self.itm_offset_for_delta) / 50) * 50

        actual_itm = abs(nifty_price - itm_strike)
        logger.info(f"[DELTA MODE] Selecting {option_type} | Nifty: {nifty_price:.2f} | Strike: {itm_strike} | ITM: {actual_itm:.2f} pts")

        itm_symbol = self.build_tradingsymbol(itm_strike, option_type, expiry)
        itm_premium = self.get_option_premium(itm_symbol)

        if itm_premium is None:
            logger.error(f"Could not get premium for {itm_symbol}")
            return None

        if itm_premium >= self.min_premium:
            logger.info(f"[DELTA MODE] ITM {itm_strike} selected | Premium: {itm_premium:.2f} | Delta ~0.7")
            return OptionContract(
                tradingsymbol=itm_symbol,
                exchange="NFO",
                strike=itm_strike,
                option_type=option_type,
                expiry=expiry,
                premium=itm_premium
            )

        # Premium too low, go deeper ITM
        logger.info(f"[DELTA MODE] ITM premium {itm_premium:.2f} < {self.min_premium}, going deeper ITM...")

        step = -50 if option_type == 'CE' else 50
        max_additional_steps = (self.max_itm_offset - self.itm_offset_for_delta) // 50

        for i in range(1, max_additional_steps + 1):
            deeper_strike = itm_strike + (step * i)
            deeper_symbol = self.build_tradingsymbol(deeper_strike, option_type, expiry)
            deeper_premium = self.get_option_premium(deeper_symbol)

            if deeper_premium is None:
                continue

            logger.info(f"[DELTA MODE] Checking deeper ITM {deeper_strike} | Premium: {deeper_premium:.2f}")

            if deeper_premium >= self.min_premium:
                logger.info(f"[DELTA MODE] Deeper ITM {deeper_strike} selected | Premium: {deeper_premium:.2f}")
                return OptionContract(
                    tradingsymbol=deeper_symbol,
                    exchange="NFO",
                    strike=deeper_strike,
                    option_type=option_type,
                    expiry=expiry,
                    premium=deeper_premium
                )

        # Fallback to original ITM strike
        logger.warning(f"[DELTA MODE] No strike with premium >= {self.min_premium}, using {itm_strike}")
        return OptionContract(
            tradingsymbol=itm_symbol,
            exchange="NFO",
            strike=itm_strike,
            option_type=option_type,
            expiry=expiry,
            premium=itm_premium
        )

    def _select_strike_premium_mode(self, nifty_price: float, signal_type: str) -> Optional[OptionContract]:
        """
        PREMIUM MODE: Target premium >= 220 for liquidity.

        Logic:
        - Start with ATM strike
        - If ATM premium >= 220, use ATM
        - If ATM premium < 220, move ITM until premium >= 220
        """
        option_type = 'CE' if signal_type == 'BUY' else 'PE'
        expiry = self.get_current_expiry()
        atm_strike = self.get_atm_strike(nifty_price)

        logger.info(f"[PREMIUM MODE] Selecting {option_type} | Nifty: {nifty_price:.2f} | ATM: {atm_strike}")

        atm_symbol = self.build_tradingsymbol(atm_strike, option_type, expiry)
        atm_premium = self.get_option_premium(atm_symbol)

        if atm_premium is None:
            logger.error(f"Could not get ATM premium for {atm_symbol}")
            return None

        if atm_premium >= self.min_premium:
            logger.info(f"[PREMIUM MODE] ATM {atm_strike} selected | Premium: {atm_premium:.2f}")
            return OptionContract(
                tradingsymbol=atm_symbol,
                exchange="NFO",
                strike=atm_strike,
                option_type=option_type,
                expiry=expiry,
                premium=atm_premium
            )

        logger.info(f"[PREMIUM MODE] ATM premium {atm_premium:.2f} < {self.min_premium}, searching ITM...")

        step = -50 if option_type == 'CE' else 50
        max_steps = self.max_itm_offset // 50

        for i in range(1, max_steps + 1):
            itm_strike = atm_strike + (step * i)
            itm_symbol = self.build_tradingsymbol(itm_strike, option_type, expiry)
            itm_premium = self.get_option_premium(itm_symbol)

            if itm_premium is None:
                continue

            logger.info(f"[PREMIUM MODE] Checking ITM {itm_strike} | Premium: {itm_premium:.2f}")

            if itm_premium >= self.min_premium:
                logger.info(f"[PREMIUM MODE] ITM {itm_strike} selected | Premium: {itm_premium:.2f}")
                return OptionContract(
                    tradingsymbol=itm_symbol,
                    exchange="NFO",
                    strike=itm_strike,
                    option_type=option_type,
                    expiry=expiry,
                    premium=itm_premium
                )

        logger.warning(f"[PREMIUM MODE] No strike with premium >= {self.min_premium}, using ATM")
        return OptionContract(
            tradingsymbol=atm_symbol,
            exchange="NFO",
            strike=atm_strike,
            option_type=option_type,
            expiry=expiry,
            premium=atm_premium
        )
