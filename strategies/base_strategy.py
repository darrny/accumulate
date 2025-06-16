from abc import ABC, abstractmethod
from typing import Dict, Optional, Tuple
import logging
from utils.binance_api import BinanceAPI
from config import TRADING_PAIR

logger = logging.getLogger(__name__)

class BaseStrategy(ABC):
    def __init__(self, api: BinanceAPI):
        self.api = api
        self.running = False
        self._trading_pair_info = None
        self._quantity_precision = None
        self._price_precision = None
        self._min_qty = None
        self._max_qty = None
        self._step_size = None
        self._min_price = None
        self._max_price = None
        self._tick_size = None
        
    def _get_trading_pair_info(self) -> Optional[Dict]:
        """Get and cache trading pair information."""
        if self._trading_pair_info is None:
            try:
                exchange_info = self.api.get_exchange_info()
                self._trading_pair_info = next(
                    (s for s in exchange_info['symbols'] if s['symbol'] == TRADING_PAIR), 
                    None
                )
                
                if self._trading_pair_info is None:
                    logger.error(f"Could not find symbol info for {TRADING_PAIR}")
                    return None
                    
                # Get all relevant filters
                for filter in self._trading_pair_info['filters']:
                    if filter['filterType'] == 'LOT_SIZE':
                        self._min_qty = float(filter['minQty'])
                        self._max_qty = float(filter['maxQty'])
                        self._step_size = float(filter['stepSize'])
                        self._quantity_precision = len(str(self._step_size).rstrip('0').split('.')[-1])
                    elif filter['filterType'] == 'PRICE_FILTER':
                        self._min_price = float(filter['minPrice'])
                        self._max_price = float(filter['maxPrice'])
                        self._tick_size = float(filter['tickSize'])
                        self._price_precision = len(str(self._tick_size).rstrip('0').split('.')[-1])
                
                logger.info(f"Trading pair info loaded:")
                logger.info(f"  Quantity - Min: {self._min_qty}, Max: {self._max_qty}, Step: {self._step_size}, Precision: {self._quantity_precision}")
                logger.info(f"  Price - Min: {self._min_price}, Max: {self._max_price}, Tick: {self._tick_size}, Precision: {self._price_precision}")
                
            except Exception as e:
                logger.error(f"Error getting trading pair info: {e}")
                return None
                
        return self._trading_pair_info
        
    def round_quantity(self, quantity: float) -> float:
        """Round quantity to appropriate precision and ensure it meets LOT_SIZE filter requirements."""
        if self._quantity_precision is None:
            self._get_trading_pair_info()
        if self._quantity_precision is None:
            logger.error("Could not determine quantity precision")
            return quantity
            
        # Ensure it's within min/max bounds
        if self._min_qty is not None:
            quantity = max(quantity, self._min_qty)
        if self._max_qty is not None:
            quantity = min(quantity, self._max_qty)
            
        # Ensure it's a multiple of step size
        if self._step_size is not None:
            # Calculate how many steps we need
            steps = round(quantity / self._step_size)
            # Convert back to quantity
            quantity = steps * self._step_size
            # Format to the correct precision
            quantity = float(f"{quantity:.{self._quantity_precision}f}")
            
        return quantity
        
    def round_price(self, price: float) -> float:
        """Round price to appropriate precision and ensure it meets PRICE_FILTER requirements."""
        if self._price_precision is None:
            self._get_trading_pair_info()
        if self._price_precision is None:
            logger.error("Could not determine price precision")
            return price
            
        # Ensure it's within min/max bounds
        if self._min_price is not None:
            price = max(price, self._min_price)
        if self._max_price is not None:
            price = min(price, self._max_price)
            
        # Ensure it's a multiple of tick size
        if self._tick_size is not None:
            # Calculate how many ticks we need
            ticks = round(price / self._tick_size)
            # Convert back to price
            price = ticks * self._tick_size
            # Format to the correct precision
            price = float(f"{price:.{self._price_precision}f}")
            
        return price
        
    @abstractmethod
    def start(self) -> None:
        """Start the strategy."""
        pass
        
    @abstractmethod
    def stop(self) -> None:
        """Stop the strategy."""
        pass