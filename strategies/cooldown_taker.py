import time
import random
import logging
from typing import Optional, Tuple
from utils.binance_api import BinanceAPI
from config import COOLDOWN_TAKER, TRADING_PAIR

logger = logging.getLogger('cooldown_taker')

class CooldownTakerStrategy:
    def __init__(self, api: BinanceAPI):
        """
        Initialize the cooldown taker strategy.
        
        Args:
            api: BinanceAPI instance for making trades
        """
        self.api = api
        self.is_running = False
        self.config = COOLDOWN_TAKER
        self.last_order_time = 0
        
    def _get_cooldown_time(self) -> float:
        """
        Get the cooldown time with random jitter.
        
        Returns:
            Cooldown time in seconds
        """
        base_time = self.config['cooldown_time']
        jitter = random.uniform(-self.config['jitter'], self.config['jitter'])
        return max(1.0, base_time + jitter)  # Ensure minimum 1 second
        
    def _get_best_ask_info(self) -> Tuple[float, float]:
        """
        Get the best ask price and quantity.
        
        Returns:
            Tuple of (price, quantity)
        """
        try:
            orderbook = self.api.get_orderbook(TRADING_PAIR, limit=1)
            best_ask_price = float(orderbook['asks'][0][0])
            best_ask_quantity = float(orderbook['asks'][0][1])
            return best_ask_price, best_ask_quantity
        except Exception as e:
            logger.error(f"Error getting best ask info: {e}")
            raise
        
    def _should_place_order(self, price: float, quantity: float) -> bool:
        """
        Determine if we should place an order based on current market conditions.
        
        Args:
            price: Current best ask price
            quantity: Current best ask quantity
            
        Returns:
            True if we should place an order, False otherwise
        """
        # Check if price is within our maximum
        if self.config['max_price'] is not None and price > self.config['max_price']:
            logger.info(f"Best ask {price} exceeds max price {self.config['max_price']}")
            return False
            
        # Check if quantity is below our maximum threshold
        if quantity > self.config['max_ask_quantity']:
            logger.info(f"Best ask quantity {quantity} is above maximum threshold {self.config['max_ask_quantity']}")
            return False
            
        return True
        
    def _calculate_order_quantity(self, ask_quantity: float) -> float:
        """
        Calculate the quantity for our order based on the ask quantity.
        
        Args:
            ask_quantity: Current best ask quantity
            
        Returns:
            Quantity for our order
        """
        # Multiply the ask quantity by our multiplier
        target_quantity = ask_quantity * self.config['order_multiplier']
        
        # Cap at maximum order quantity
        return min(target_quantity, self.config['max_order_quantity'])
        
    def _place_taker_order(self) -> None:
        """
        Place a limit order to take the best ask.
        """
        try:
            # Get current best ask info
            best_ask_price, best_ask_quantity = self._get_best_ask_info()
            
            # Check if we should place an order
            if not self._should_place_order(best_ask_price, best_ask_quantity):
                return
                
            # Calculate our order quantity
            order_quantity = self._calculate_order_quantity(best_ask_quantity)
            
            # Place limit order
            order = self.api.place_limit_order(
                pair=TRADING_PAIR,
                price=best_ask_price,
                quantity=order_quantity,
                side='BUY',
                post_only=False  # We want to take liquidity
            )
            
            logger.info(f"Placed taker order at {best_ask_price} for {order_quantity} {TRADING_PAIR}")
            self.last_order_time = time.time()
            
        except Exception as e:
            logger.error(f"Error placing taker order: {e}")
    
    def start(self) -> None:
        """Start the cooldown taker strategy."""
        if not self.config['enabled']:
            logger.info("Cooldown taker strategy is disabled")
            return
            
        self.is_running = True
        self.last_order_time = 0
        logger.info("Starting cooldown taker strategy")
        
        while self.is_running:
            try:
                current_time = time.time()
                time_since_last_order = current_time - self.last_order_time
                
                # Check if cooldown period has elapsed
                if time_since_last_order >= self._get_cooldown_time():
                    self._place_taker_order()
                
                # Sleep for a short time to prevent excessive API calls
                time.sleep(1)
                
            except Exception as e:
                logger.error(f"Error in cooldown taker strategy: {e}")
                time.sleep(1)
    
    def stop(self) -> None:
        """Stop the cooldown taker strategy."""
        self.is_running = False
        logger.info("Stopping cooldown taker strategy")
