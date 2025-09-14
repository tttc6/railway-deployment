import logging
from datetime import datetime, timezone
from typing import Any, Dict

logger = logging.getLogger(__name__)


class TradingBot:
    """Pure trading bot business logic, free from infrastructure concerns"""

    def __init__(self):
        self.running = False
        self.positions = {}
        self.pnl = 0.0

    def start_trading(self):
        """Start the trading bot"""
        self.running = True

    def stop_trading(self):
        """Stop the trading bot"""
        self.running = False

    @property
    def is_running(self) -> bool:
        """Check if bot is currently running"""
        return self.running

    def update_pnl(self, change: float):
        """Update PnL with a change amount"""
        self.pnl += change

    def process_market_data(self, data: str):
        """Process market data and make trading decisions"""
        pass

    def execute_trade(self, trade_data: Dict[str, Any]):
        """Execute trades via broker API"""
        logger.info(f"Executing trade: {trade_data}")

    def get_status(self) -> Dict[str, str]:
        """Get current bot status as a string dictionary for Redis storage"""
        return {
            "running": str(self.running),
            "pnl": str(self.pnl),
            "positions": str(len(self.positions)),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
