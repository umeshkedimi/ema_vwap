#!/usr/bin/env python3
"""
Kite Connect API Client for Zerodha.
Handles quotes, order placement, and position tracking.
"""

import logging
import time
import requests
from typing import Optional

logger = logging.getLogger(__name__)


class KiteAPI:
    """Kite Connect API client for order execution and quotes."""

    BASE_URL = "https://api.kite.trade"

    def __init__(self, api_key: str, access_token: str):
        self.api_key = api_key
        self.access_token = access_token
        self.headers = {
            "X-Kite-Version": "3",
            "Authorization": f"token {api_key}:{access_token}"
        }

    def get_profile(self) -> dict:
        """
        Get user profile to validate token.
        Returns: {"status": "success", "data": {"user_name": "...", ...}} or error
        """
        url = f"{self.BASE_URL}/user/profile"

        try:
            response = requests.get(url, headers=self.headers)
            return response.json()
        except Exception as e:
            logger.error(f"Kite profile request failed: {e}")
            return {"status": "error", "message": str(e)}

    def get_ltp(self, symbols: list) -> dict:
        """
        Get Last Traded Price for symbols.
        symbols: List of symbols like ['NFO:NIFTY2642224500CE']
        Returns: {'NFO:NIFTY2642224500CE': {'last_price': 245.5}}
        """
        url = f"{self.BASE_URL}/quote/ltp"
        params = [("i", sym) for sym in symbols]

        try:
            response = requests.get(url, headers=self.headers, params=params)
            result = response.json()

            if result.get("status") == "success":
                return result.get("data", {})
            else:
                logger.error(f"Kite LTP error: {result}")
                return {}
        except Exception as e:
            logger.error(f"Kite LTP request failed: {e}")
            return {}

    def get_quote(self, symbols: list) -> dict:
        """
        Get full quote for symbols.
        Returns more details including OHLC, volume, etc.
        """
        url = f"{self.BASE_URL}/quote"
        params = [("i", sym) for sym in symbols]

        try:
            response = requests.get(url, headers=self.headers, params=params)
            result = response.json()

            if result.get("status") == "success":
                return result.get("data", {})
            else:
                logger.error(f"Kite quote error: {result}")
                return {}
        except Exception as e:
            logger.error(f"Kite quote request failed: {e}")
            return {}

    def place_order(
        self,
        tradingsymbol: str,
        exchange: str,
        transaction_type: str,
        quantity: int,
        order_type: str = "MARKET",
        product: str = "MIS",
        price: float = None,
        trigger_price: float = None,
        validity: str = "DAY",
        tag: str = None,
        market_protection: int = 2
    ) -> dict:
        """
        Place an order on Kite.

        Args:
            tradingsymbol: e.g., "NIFTY2642224500CE"
            exchange: "NFO" for options
            transaction_type: "BUY" or "SELL"
            quantity: Number of shares/lots
            order_type: "MARKET", "LIMIT", "SL", "SL-M"
            product: "MIS" (intraday), "NRML" (overnight), "CNC" (delivery)
            price: Required for LIMIT orders
            trigger_price: Required for SL/SL-M orders
            validity: "DAY" or "IOC"
            tag: Optional order tag (max 20 chars)
            market_protection: Protection % for MARKET orders (default 2%)

        Returns:
            {"status": "success", "data": {"order_id": "123"}} or error
        """
        url = f"{self.BASE_URL}/orders/regular"

        data = {
            "tradingsymbol": tradingsymbol,
            "exchange": exchange,
            "transaction_type": transaction_type,
            "order_type": order_type,
            "quantity": quantity,
            "product": product,
            "validity": validity
        }

        if price is not None:
            data["price"] = price
        if trigger_price is not None:
            data["trigger_price"] = trigger_price
        if tag:
            data["tag"] = tag[:20]
        if order_type == "MARKET" and market_protection is not None:
            data["market_protection"] = market_protection

        try:
            response = requests.post(url, headers=self.headers, data=data)
            result = response.json()

            if result.get("status") == "success":
                order_id = result.get("data", {}).get("order_id")
                logger.info(f"Order placed: {order_id} - {transaction_type} {quantity} {tradingsymbol}")
                return result
            else:
                logger.error(f"Order failed: {result}")
                return result
        except Exception as e:
            logger.error(f"Order request failed: {e}")
            return {"status": "error", "message": str(e)}

    def get_positions(self) -> dict:
        """
        Get all positions.
        Returns: {"net": [...], "day": [...]}
        """
        url = f"{self.BASE_URL}/portfolio/positions"

        try:
            response = requests.get(url, headers=self.headers)
            result = response.json()

            if result.get("status") == "success":
                return result.get("data", {})
            else:
                logger.error(f"Positions error: {result}")
                return {}
        except Exception as e:
            logger.error(f"Positions request failed: {e}")
            return {}

    def get_orders(self) -> list:
        """
        Get all orders for the day.
        Returns: List of orders
        """
        url = f"{self.BASE_URL}/orders"

        try:
            response = requests.get(url, headers=self.headers)
            result = response.json()

            if result.get("status") == "success":
                return result.get("data", [])
            else:
                logger.error(f"Orders error: {result}")
                return []
        except Exception as e:
            logger.error(f"Orders request failed: {e}")
            return []

    def get_order_history(self, order_id: str) -> list:
        """
        Get history of a specific order.
        Returns: List of order state changes
        """
        url = f"{self.BASE_URL}/orders/{order_id}"

        try:
            response = requests.get(url, headers=self.headers)
            result = response.json()

            if result.get("status") == "success":
                return result.get("data", [])
            else:
                logger.error(f"Order history error: {result}")
                return []
        except Exception as e:
            logger.error(f"Order history request failed: {e}")
            return []

    def get_fill_price(self, order_id: str, max_retries: int = 5) -> Optional[float]:
        """
        Get the actual fill price for an order.
        Retries until order is COMPLETE or max retries reached.
        Returns: average_price if filled, None otherwise
        """
        for i in range(max_retries):
            history = self.get_order_history(order_id)
            if history:
                # Get the latest state (last item in history)
                latest = history[-1]
                if latest.get('status') == 'COMPLETE':
                    avg_price = latest.get('average_price')
                    logger.info(f"Order {order_id} filled at {avg_price}")
                    return avg_price
                elif latest.get('status') in ['REJECTED', 'CANCELLED']:
                    logger.error(f"Order {order_id} {latest.get('status')}: {latest.get('status_message')}")
                    return None
            time.sleep(0.5)  # Wait before retry

        logger.warning(f"Order {order_id} not filled after {max_retries} retries")
        return None
