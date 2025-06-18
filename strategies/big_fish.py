import logging
import time
import random
from typing import Optional, Tuple, Dict
from utils.binance_api import BinanceAPI
from utils.colors import Colors
from config import TRADING_PAIR, BIG_FISH, MAX_PRICE, TARGET_QUANTITY, BASE, QUOTE
from .base_strategy import BaseStrategy

logger = logging.getLogger(__name__)

class BigFishStrategy(BaseStrategy):
    def __init__(self, api: BinanceAPI, monitor=None):
        super().__init__(api, monitor)
        self.config = BIG_FISH
        self.last_order_time = 0
        
    def _get_cooldown_time(self) -> float:
        """
        Get cooldown time with jitter.
        """
        base_time = self.config['cooldown_time']
        jitter = self.config['jitter']
        return base_time + random.uniform(-jitter, jitter)
        
    def _get_remaining_quantity(self) -> float:
        """
        Get the remaining quantity we need to acquire.
        """
        try:
            current_quantity = float(self.api.get_account_balance(BASE).get('free', 0))
            remaining = TARGET_QUANTITY - current_quantity
            return max(0, remaining)
        except Exception as e:
            logger.error(f"{Colors.RED}Error getting remaining quantity: {e}{Colors.ENDC}")
            return 0
        
    def _should_place_order(self, ask_price: float, ask_quantity: float) -> bool:
        """
        Check if we should place an order based on price and quantity.
        """
        # Check if price is within our limit
        if ask_price > MAX_PRICE:
            return False
            
        # Get remaining quantity
        remaining = self._get_remaining_quantity()
        if remaining <= 0:
            return False
            
        # Check if quantity is above our minimum percentage
        min_volume = remaining * self.config['min_volume_percentage']
        if ask_quantity < min_volume:
            return False
            
        return True
        
    def _calculate_order_quantity(self, orderbook: Dict) -> float:
        """Calculate the quantity for our taker order."""
        try:
            # Get the best ask
            best_ask = float(orderbook['asks'][0][0]) if orderbook['asks'] else 0
            best_ask_qty = float(orderbook['asks'][0][1]) if orderbook['asks'] else 0
            
            # Calculate percentage-based quantity
            remaining = self.get_remaining_quantity()
            percentage_quantity = remaining * self.config['order_size_percentage']
            
            # Use the smaller of the two quantities
            quantity = min(best_ask_qty, percentage_quantity)
            
            # Apply maximum order size limit
            max_order_size = self.config.get('max_order_size', float('inf'))
            quantity = min(quantity, max_order_size)
            
            # Round to appropriate decimal places
            return self.round_quantity(quantity)
            
        except Exception as e:
            logger.error(f"{Colors.RED}Error calculating order quantity: {str(e)}{Colors.ENDC}")
            return 0.0
        
    def _place_taker_order(self) -> None:
        """Place a taker order."""
        try:
            # Get current orderbook
            orderbook = self.api.get_orderbook(TRADING_PAIR)
            if not orderbook['asks']:
                return
                
            # Get best ask
            best_ask_price = float(orderbook['asks'][0][0])
            best_ask_qty = float(orderbook['asks'][0][1])
            
            # Check if we should place an order
            if not self._should_place_order(best_ask_price, best_ask_qty):
                return
                
            # Calculate order quantity
            quantity = self._calculate_order_quantity(orderbook)
            if quantity <= 0:
                return
                
            # Place market order
            order = self.api.place_market_order(
                pair=TRADING_PAIR,
                quantity=quantity,
                side='BUY'
            )
            
            # Update acquired quantity if in standalone mode
            if self.monitor is None:
                self.update_acquired_quantity(quantity)
            
            logger.info(f"{Colors.PINK}Placed taker order for {quantity} {BASE} at market price{Colors.ENDC}")
            
            self.last_order_time = time.time()
            
        except Exception as e:
            logger.error(f"{Colors.RED}Error placing taker order: {str(e)}{Colors.ENDC}")
            
    def _log_orderbook_state(self) -> None:
        """Log the current orderbook state."""
        try:
            orderbook = self.api.get_orderbook(TRADING_PAIR, limit=5)
            
            logger.info(f"\n{Colors.BOLD}Top 5 Bids:{Colors.ENDC}")
            for price, qty in orderbook['bids'][:5]:
                logger.info(f"  {price} {QUOTE} - {qty} {BASE}")
            logger.info(f"\n{Colors.BOLD}Top 5 Asks:{Colors.ENDC}")
            for price, qty in orderbook['asks'][:5]:
                logger.info(f"  {price} {QUOTE} - {qty} {BASE}")
            logger.info(f"{Colors.BOLD}============================={Colors.ENDC}")
        except Exception as e:
            logger.error(f"{Colors.RED}Error logging orderbook state: {e}{Colors.ENDC}")
        
    def start(self) -> None:
        """
        Start the strategy.
        """
        logger.info(f"{Colors.GOLDEN}Starting big fish strategy for {TRADING_PAIR}{Colors.ENDC}")
        self.running = True
        
        while self.running:
            try:
                # Check if we're in cooldown
                if time.time() - self.last_order_time < self._get_cooldown_time():
                    time.sleep(1)
                    continue
                    
                # Try to place an order
                self._place_taker_order()
                
                # Sleep to avoid hitting rate limits
                time.sleep(1)
                
            except Exception as e:
                logger.error(f"{Colors.RED}Error in big fish strategy: {e}{Colors.ENDC}")
                time.sleep(1)
                
    def stop(self) -> None:
        """
        Stop the strategy.
        """
        logger.info(f"{Colors.GOLDEN}Stopping big fish strategy{Colors.ENDC}")
        self.running = False
