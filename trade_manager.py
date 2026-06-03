#!/usr/bin/env python3
"""
Trade Manager for Nifty Options Trading.
Handles trade execution, rules enforcement, and position monitoring.
Uses Kite Connect API for order execution.
"""

import os
import logging
import uuid
from datetime import datetime, date, time
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum

logger = logging.getLogger(__name__)


class TradeStatus(Enum):
    PENDING = "pending"
    OPEN = "open"
    TARGET_HIT = "target_hit"
    SL_HIT = "sl_hit"
    CLOSED = "closed"


@dataclass
class Trade:
    """Represents a single trade."""
    trade_id: str
    signal_type: str
    tradingsymbol: str
    exchange: str
    option_type: str
    strike: int
    entry_price: float
    target_price: float
    stoploss_price: float
    quantity: int
    entry_time: datetime
    exit_time: Optional[datetime] = None
    exit_price: Optional[float] = None
    status: TradeStatus = TradeStatus.PENDING
    pnl: float = 0.0
    order_id: Optional[str] = None
    exit_order_id: Optional[str] = None
    sl_at_breakeven: bool = False
    trailing_sl_level: int = 0


@dataclass
class DailyState:
    """Tracks daily trading state."""
    date: date
    trades: list = field(default_factory=list)
    trades_executed: int = 0
    first_trade_profit_exit: bool = False
    open_trade: Optional[Trade] = None


class TradeManager:
    """Manages trade execution and rules enforcement using Kite Connect."""

    BREAKEVEN_TRIGGER_POINTS = 50

    def __init__(self, kite_api, option_selector, telegram, config):
        self.kite = kite_api
        self.option_selector = option_selector
        self.telegram = telegram
        self.config = config
        self.daily_state: Optional[DailyState] = None
        self._init_daily_state()

    def _init_daily_state(self):
        """Initialize or reset daily state if new day."""
        today = date.today()
        if self.daily_state is None or self.daily_state.date != today:
            self.daily_state = DailyState(date=today)
            logger.info(f"Daily state initialized for {today}")

    def _generate_trade_id(self) -> str:
        """Generate unique trade ID."""
        today = date.today().strftime('%Y%m%d')
        return f"T{today}_{uuid.uuid4().hex[:6].upper()}"

    def is_trading_time(self) -> bool:
        """Check if current time allows trading."""
        now = datetime.now().time()
        start = time(
            int(self.config['trade_start_time'].split(':')[0]),
            int(self.config['trade_start_time'].split(':')[1])
        )
        end = time(
            int(self.config['trade_end_time'].split(':')[0]),
            int(self.config['trade_end_time'].split(':')[1])
        )
        return start <= now <= end

    def can_execute_trade(self) -> tuple:
        """
        Check if a trade can be executed.
        Returns: (can_trade: bool, reason: str)
        """
        self._init_daily_state()

        if not self.is_trading_time():
            return False, f"Outside trading hours ({self.config['trade_start_time']} - {self.config['trade_end_time']})"

        if self.daily_state.open_trade is not None:
            return False, "Trade already open - wait for exit"

        if self.daily_state.trades_executed >= self.config['max_trades_per_day']:
            return False, f"Max {self.config['max_trades_per_day']} trades reached for today"

        if self.daily_state.first_trade_profit_exit:
            return False, "First trade exited with profit - no more trades today"

        return True, "Trade allowed"

    def process_signal(self, signal: dict) -> Optional[Trade]:
        """
        Process a new signal and execute trade if rules allow.
        Returns: Trade object if executed, None if skipped.
        """
        can_trade, reason = self.can_execute_trade()

        if not can_trade:
            logger.info(f"Signal skipped: {reason}")
            self.telegram.send_message(
                f"Signal received but NOT traded\n\n"
                f"Type: {signal['type']}\n"
                f"Reason: {reason}"
            )
            return None

        option = self.option_selector.select_strike(
            nifty_price=signal['price'],
            signal_type=signal['type']
        )

        if option is None:
            logger.error("Failed to select option strike")
            self.telegram.send_message("Trade FAILED: Could not select option strike")
            return None

        trade = Trade(
            trade_id=self._generate_trade_id(),
            signal_type=signal['type'],
            tradingsymbol=option.tradingsymbol,
            exchange=option.exchange,
            option_type=option.option_type,
            strike=option.strike,
            entry_price=option.premium,
            target_price=option.premium + self.config['target_points'],
            stoploss_price=max(option.premium - self.config['stoploss_points'], 1),
            quantity=self.config['lot_size'],
            entry_time=datetime.now()
        )

        success = self._execute_entry(trade)

        if success:
            trade.status = TradeStatus.OPEN
            self.daily_state.open_trade = trade
            self.daily_state.trades.append(trade)
            self.daily_state.trades_executed += 1
            self._send_entry_notification(trade)
            logger.info(f"Trade executed: {trade.trade_id} - {trade.tradingsymbol}")
        else:
            logger.error(f"Trade execution failed: {trade.trade_id}")

        return trade if success else None

    def _execute_entry(self, trade: Trade) -> bool:
        """Execute entry order (paper or real)."""
        if self.config['paper_trading']:
            logger.info(f"PAPER TRADE: BUY {trade.quantity} {trade.tradingsymbol} @ {trade.entry_price}")
            return True
        else:
            return self._real_entry(trade)

    def _real_entry(self, trade: Trade) -> bool:
        """Place real order via Kite Connect API."""
        try:
            response = self.kite.place_order(
                tradingsymbol=trade.tradingsymbol,
                exchange=trade.exchange,
                transaction_type="BUY",
                quantity=trade.quantity,
                order_type="MARKET",
                product="MIS",
                validity="DAY",
                tag=trade.trade_id[:20]
            )

            if response.get('status') == 'success':
                trade.order_id = response.get('data', {}).get('order_id')
                logger.info(f"Kite order placed: {trade.order_id}")
                return True
            else:
                error_msg = response.get('message', 'Unknown error')
                logger.error(f"Kite order failed: {response}")
                self.telegram.send_message(f"ORDER FAILED: {error_msg}")
                return False
        except Exception as e:
            logger.error(f"Order execution error: {e}")
            self.telegram.send_message(f"ORDER ERROR: {str(e)}")
            return False

    def monitor_open_trade(self):
        """Check open trade for SL hit, breakeven, and trailing SL."""
        if self.daily_state.open_trade is None:
            return

        trade = self.daily_state.open_trade

        if trade.status != TradeStatus.OPEN:
            return

        current_price = self._get_option_price(trade.tradingsymbol)

        if current_price is None:
            logger.warning(f"Could not get price for {trade.tradingsymbol}")
            return

        current_profit = current_price - trade.entry_price
        logger.debug(f"Monitoring {trade.tradingsymbol}: LTP={current_price:.2f}, Profit={current_profit:.2f}, SL={trade.stoploss_price:.2f}")

        if current_price <= trade.stoploss_price:
            self._close_trade(trade, current_price, TradeStatus.SL_HIT)
            return

        if not trade.sl_at_breakeven and current_profit >= self.BREAKEVEN_TRIGGER_POINTS:
            trade.stoploss_price = trade.entry_price
            trade.sl_at_breakeven = True
            logger.info(f"SL moved to breakeven: {trade.entry_price:.2f}")
            self.telegram.send_message(
                f"SL MOVED TO BREAKEVEN\n\n"
                f"Option: NIFTY {trade.strike} {trade.option_type}\n"
                f"LTP: {current_price:.2f} (+{self.BREAKEVEN_TRIGGER_POINTS:.0f} triggered)\n"
                f"New SL: {trade.stoploss_price:.2f} (entry)\n"
                f"Trailing starts at: +75 pts"
            )

        if current_profit >= 75:
            new_trailing_level = int((current_profit // 25) * 25)
            if new_trailing_level > trade.trailing_sl_level:
                trade.trailing_sl_level = new_trailing_level
                new_sl = trade.entry_price + (new_trailing_level - 25)
                if new_sl > trade.stoploss_price:
                    trade.stoploss_price = new_sl
                    logger.info(f"Trailing SL moved to: {new_sl:.2f} (locking +{new_trailing_level - 25:.0f} pts)")
                    self.telegram.send_message(
                        f"TRAILING SL UPDATED\n\n"
                        f"Option: NIFTY {trade.strike} {trade.option_type}\n"
                        f"LTP: {current_price:.2f} (+{current_profit:.0f} pts)\n"
                        f"New SL: {trade.stoploss_price:.2f} (locking +{new_trailing_level - 25:.0f} profit)\n"
                        f"Next trail at: +{new_trailing_level + 25:.0f} pts"
                    )

    def _get_option_price(self, tradingsymbol: str) -> Optional[float]:
        """Get current price for an option using Kite API."""
        try:
            symbol_with_exchange = f"NFO:{tradingsymbol}"
            result = self.kite.get_ltp([symbol_with_exchange])

            if result and symbol_with_exchange in result:
                return result[symbol_with_exchange].get('last_price')
            return None
        except Exception as e:
            logger.warning(f"Error getting quote: {e}")
            return None

    def _close_trade(self, trade: Trade, exit_price: float, status: TradeStatus):
        """Close a trade with given status."""
        trade.exit_price = exit_price
        trade.exit_time = datetime.now()
        trade.status = status
        trade.pnl = (exit_price - trade.entry_price) * trade.quantity

        if not self.config['paper_trading']:
            self._execute_exit(trade)

        if trade.pnl > 0 and self.daily_state.trades_executed == 1:
            self.daily_state.first_trade_profit_exit = True

        self._send_exit_notification(trade)
        self.daily_state.open_trade = None

        logger.info(f"Trade closed: {trade.trade_id} - {status.value} - PnL: {trade.pnl:.2f}")

    def force_close_all_positions(self):
        """Force close any open position at 3:15 PM."""
        if self.daily_state.open_trade is None:
            return

        trade = self.daily_state.open_trade
        if trade.status != TradeStatus.OPEN:
            return

        current_price = self._get_option_price(trade.tradingsymbol)
        if current_price is None:
            current_price = trade.entry_price
            logger.warning(f"Could not get exit price, using entry price")

        trade.exit_price = current_price
        trade.exit_time = datetime.now()
        trade.status = TradeStatus.CLOSED
        trade.pnl = (current_price - trade.entry_price) * trade.quantity

        if not self.config['paper_trading']:
            self._execute_exit(trade)

        points = current_price - trade.entry_price
        pnl_sign = "+" if trade.pnl >= 0 else ""

        message = (
            f"POSITION SQUARED OFF (3:15 PM)\n\n"
            f"Option: NIFTY {trade.strike} {trade.option_type}\n"
            f"Entry: {trade.entry_price:.2f}\n"
            f"Exit: {current_price:.2f}\n"
            f"P&L: {pnl_sign}{trade.pnl:.2f} ({points:+.2f} x {trade.quantity})"
        )
        self.telegram.send_message(message)
        self.daily_state.open_trade = None

        logger.info(f"Position force closed at 3:15 PM: {trade.trade_id} - PnL: {trade.pnl:.2f}")

    def is_trading_day_complete(self) -> bool:
        """Check if trading is done for the day (no more trades possible)."""
        if self.daily_state.open_trade is not None:
            return False

        if self.daily_state.first_trade_profit_exit:
            return True

        if self.daily_state.trades_executed >= self.config['max_trades_per_day']:
            return True

        return False

    def get_status_message(self) -> str:
        """Get current bot status for heartbeat."""
        now = datetime.now().strftime('%H:%M:%S')

        if self.daily_state.open_trade:
            trade = self.daily_state.open_trade
            current_price = self._get_option_price(trade.tradingsymbol)
            if current_price:
                unrealized_pnl = (current_price - trade.entry_price) * trade.quantity
                current_profit = current_price - trade.entry_price
                pnl_sign = "+" if unrealized_pnl >= 0 else ""
                if trade.trailing_sl_level > 0:
                    next_trail = trade.trailing_sl_level + 25
                    trail_info = f"Trail: +{next_trail:.0f}"
                elif trade.sl_at_breakeven:
                    trail_info = "Trail: +75"
                else:
                    trail_info = "BE: +50"
                return (
                    f"Status [{now}]\n"
                    f"OPEN: {trade.strike} {trade.option_type}\n"
                    f"Entry: {trade.entry_price:.2f} | LTP: {current_price:.2f}\n"
                    f"SL: {trade.stoploss_price:.2f} | {trail_info}\n"
                    f"Unrealized: {pnl_sign}{unrealized_pnl:.2f}"
                )
            else:
                return f"Status [{now}] OPEN position (price fetch failed)"
        else:
            total_pnl = sum(t.pnl for t in self.daily_state.trades)
            pnl_str = f"+{total_pnl:.2f}" if total_pnl >= 0 else f"{total_pnl:.2f}"
            return (
                f"Status [{now}]\n"
                f"No open position\n"
                f"Trades: {self.daily_state.trades_executed}/{self.config['max_trades_per_day']}\n"
                f"Day P&L: {pnl_str}"
            )

    def _execute_exit(self, trade: Trade) -> bool:
        """Execute exit order via Kite Connect."""
        try:
            response = self.kite.place_order(
                tradingsymbol=trade.tradingsymbol,
                exchange=trade.exchange,
                transaction_type="SELL",
                quantity=trade.quantity,
                order_type="MARKET",
                product="MIS",
                validity="DAY",
                tag=f"EXIT_{trade.trade_id[:14]}"
            )

            if response.get('status') == 'success':
                trade.exit_order_id = response.get('data', {}).get('order_id')
                logger.info(f"Exit order placed: {trade.exit_order_id}")
                return True
            else:
                logger.error(f"Exit order failed: {response}")
                return False
        except Exception as e:
            logger.error(f"Exit order error: {e}")
            return False

    def _send_entry_notification(self, trade: Trade):
        """Send Telegram notification for trade entry."""
        mode = "PAPER" if self.config['paper_trading'] else "LIVE"
        trade_num = self.daily_state.trades_executed

        message = (
            f"{'BUY' if trade.signal_type == 'BUY' else 'SELL'} TRADE EXECUTED (#{trade_num}/{self.config['max_trades_per_day']})\n\n"
            f"Option: NIFTY {trade.strike} {trade.option_type}\n"
            f"Symbol: {trade.tradingsymbol}\n"
            f"Entry: {trade.entry_price:.2f}\n"
            f"SL: {trade.stoploss_price:.2f} (-{self.config['stoploss_points']})\n"
            f"BE Trigger: +{self.BREAKEVEN_TRIGGER_POINTS} pts\n"
            f"Trail starts: +75 pts (then every 25)\n"
            f"Qty: {trade.quantity}\n\n"
            f"Mode: {mode}"
        )
        self.telegram.send_message(message)

    def _send_exit_notification(self, trade: Trade):
        """Send Telegram notification for trade exit."""
        if trade.status == TradeStatus.SL_HIT:
            if trade.trailing_sl_level > 0:
                emoji = "TRAILING SL HIT"
            elif trade.sl_at_breakeven:
                emoji = "BREAKEVEN EXIT"
            else:
                emoji = "STOPLOSS HIT"
        else:
            emoji = "TRADE CLOSED"

        pnl_sign = "+" if trade.pnl >= 0 else ""
        points = trade.exit_price - trade.entry_price

        message = (
            f"{emoji}\n\n"
            f"Option: NIFTY {trade.strike} {trade.option_type}\n"
            f"Entry: {trade.entry_price:.2f}\n"
            f"Exit: {trade.exit_price:.2f}\n"
            f"P&L: {pnl_sign}{trade.pnl:.2f} ({points:+.2f} x {trade.quantity})\n"
        )

        if trade.pnl > 0 and self.daily_state.trades_executed == 1:
            message += "\nNo more trades today (profit exit)"
        elif trade.pnl <= 0 and self.daily_state.trades_executed < self.config['max_trades_per_day']:
            message += f"\n{self.config['max_trades_per_day'] - self.daily_state.trades_executed} trade(s) remaining"

        self.telegram.send_message(message)

    def get_daily_summary(self) -> str:
        """Generate end-of-day summary."""
        if not self.daily_state.trades:
            return "No trades executed today."

        total_pnl = sum(t.pnl for t in self.daily_state.trades)
        pnl_sign = "+" if total_pnl >= 0 else ""

        summary = f"Daily Summary - {self.daily_state.date}\n\n"
        summary += f"Trades: {self.daily_state.trades_executed}/{self.config['max_trades_per_day']}\n\n"

        for i, trade in enumerate(self.daily_state.trades, 1):
            status_emoji = "" if trade.status == TradeStatus.TARGET_HIT else ""
            summary += (
                f"Trade #{i}: NIFTY {trade.strike} {trade.option_type}\n"
                f"  {trade.entry_time.strftime('%H:%M')} -> {trade.exit_time.strftime('%H:%M') if trade.exit_time else 'OPEN'}\n"
                f"  {status_emoji} {trade.status.value.upper()}\n"
                f"  P&L: {'+' if trade.pnl >= 0 else ''}{trade.pnl:.2f}\n\n"
            )

        summary += f"Total P&L: {pnl_sign}{total_pnl:.2f}"
        mode = "PAPER" if self.config['paper_trading'] else "LIVE"
        summary += f"\nMode: {mode}"

        return summary
