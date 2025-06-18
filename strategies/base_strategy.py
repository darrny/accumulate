from abc import ABC, abstractmethod
from typing import Dict, Optional, Tuple
import logging
from utils.binance_api import BinanceAPI
from config import TRADING_PAIR, TARGET_QUANTITY, BASE, QUOTE
from utils.colors import Colors

logger = logging.getLogger(__name__)

class BaseStrategy(ABC):
    def __init__(self, api: BinanceAPI, monitor=None):
        self.api = api
        self.monitor = monitor
        self.running = False
        self.thread = None
        self.target_quantity = TARGET_QUANTITY  # Add target quantity from config
        self._trading_pair_info = None
        self._load_trading_pair_info()
        self.last_order_time = 0
        self._quantity_precision = None
        self._price_precision = None
        self._min_qty = None
        self._max_qty = None
        self._step_size = None
        self._min_price = None
        self._max_price = None
        self._tick_size = None
        self._acquired_quantity = 0.0  # Track acquired quantity for standalone mode
        
    def _load_trading_pair_info(self):
        """Load trading pair information from exchange."""
        try:
            # Get exchange info
            exchange_info = self.api.client.get_exchange_info()
            
            # Find our trading pair
            for symbol in exchange_info['symbols']:
                if symbol['symbol'] == TRADING_PAIR:
                    self._trading_pair_info = symbol
                    
                    # Log the trading pair info
                    logger.info(f"Trading pair info loaded for {TRADING_PAIR}:")
                    
                    # Log base asset info
                    base_asset = symbol['baseAsset']
                    base_info = next((f for f in symbol['filters'] if f['filterType'] == 'LOT_SIZE'), None)
                    if base_info:
                        logger.info(f"  {base_asset} - Min: {base_info['minQty']}, Max: {base_info['maxQty']}, "
                                  f"Step: {base_info['stepSize']}, Precision: {len(base_info['stepSize'].split('.')[-1].rstrip('0'))}")
                    
                    # Log quote asset info
                    quote_asset = symbol['quoteAsset']
                    price_info = next((f for f in symbol['filters'] if f['filterType'] == 'PRICE_FILTER'), None)
                    if price_info:
                        logger.info(f"  {quote_asset} - Min: {price_info['minPrice']}, Max: {price_info['maxPrice']}, "
                                  f"Tick: {price_info['tickSize']}, Precision: {len(price_info['tickSize'].split('.')[-1].rstrip('0'))}")
                    break
                    
        except Exception as e:
            logger.error(f"Error loading trading pair info: {e}")
        
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
                
                logger.info(f"Trading pair info loaded for {TRADING_PAIR}:")
                logger.info(f"  {BASE} - Min: {self._min_qty}, Max: {self._max_qty}, Step: {self._step_size}, Precision: {self._quantity_precision}")
                logger.info(f"  {QUOTE} - Min: {self._min_price}, Max: {self._max_price}, Tick: {self._tick_size}, Precision: {self._price_precision}")
                
            except Exception as e:
                logger.error(f"Error getting trading pair info: {e}")
                return None
                
        return self._trading_pair_info
        
    def round_quantity(self, quantity: float) -> float:
        """Round quantity to appropriate decimal places."""
        if self._quantity_precision is None:
            self._get_trading_pair_info()
        return round(quantity, self._quantity_precision) if self._quantity_precision is not None else quantity
        
    def round_price(self, price: float) -> float:
        """Round price to appropriate decimal places."""
        if self._price_precision is None:
            self._get_trading_pair_info()
        return round(price, self._price_precision) if self._price_precision is not None else price
        
    def get_remaining_quantity(self) -> float:
        """Get remaining quantity to acquire."""
        if self.monitor is not None:
            return self.monitor.get_remaining_quantity()
        else:
            # Standalone mode: use local tracking
            return max(0, TARGET_QUANTITY - self._acquired_quantity)
            
    def update_acquired_quantity(self, quantity: float) -> None:
        """Update the acquired quantity (for standalone mode)."""
        self._acquired_quantity += quantity
        
    def _update_progress(self) -> None:
        """Update progress via REST API."""
        try:
            if self.monitor is not None:
                self.monitor._log_progress()
        except Exception as e:
            logger.error(f"{Colors.RED}Error updating progress: {e}{Colors.ENDC}")
        
    @abstractmethod
    def start(self) -> None:
        """Start the strategy."""
        self.running = True
        
    @abstractmethod
    def stop(self) -> None:
        """Stop the strategy."""
        self.running = False