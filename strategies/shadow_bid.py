import time
import random
import logging
from typing import Optional
from utils.binance_api import BinanceAPI
from config import SHADOW_BID, TRADING_PAIR

logger = logging.getLogger('shadow_bid')

class ShadowBidStrategy:
    def __init__(self, api: BinanceAPI):
        """
        Initialize the shadow bid strategy.
        
        Args:
            api: BinanceAPI instance for making trades
        """
        self.api = api
        self.current_order_id: Optional[int] = None
        self.is_running = False
        self.config = SHADOW_BID
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
        
    def _place_shadow_order(self, price: float) -> None:
        """
        Place a new shadow bid order at the specified price.
        
        Args:
            price: Price to place the order at
        """
        try:
            current_time = time.time()
            time_since_last_order = current_time - self.last_order_time
            
            # Check if cooldown period has elapsed
            if time_since_last_order < self._get_cooldown_time():
                logger.info(f"Cooldown in effect, waiting before placing new order")
                return
                
            # Cancel existing order if it exists
            if self.current_order_id is not None:
                try:
                    self.api.cancel_order(TRADING_PAIR, self.current_order_id)
                    logger.info(f"Cancelled previous shadow bid order {self.current_order_id}")
                except Exception as e:
                    logger.warning(f"Failed to cancel previous order {self.current_order_id}: {e}")
                    # If order was already filled, that's fine - we'll just place a new one
            
            # Place new order
            order = self.api.place_limit_order(
                pair=TRADING_PAIR,
                price=price,
                quantity=self.config['quantity'],
                side='BUY',
                post_only=True
            )
            
            self.current_order_id = order['orderId']
            self.last_order_time = current_time
            logger.info(f"Placed new shadow bid order {self.current_order_id} at {price}")
            
        except Exception as e:
            logger.error(f"Error placing shadow bid order: {e}")
            self.current_order_id = None
    
    def _get_shadow_price(self) -> float:
        """
        Get the price at which to place the shadow bid.
        This will be the best bid price, or max_price if specified.
        
        Returns:
            Price to place the shadow bid at
        """
        try:
            best_bid, _ = self.api.get_best_bid_ask(TRADING_PAIR)
            if self.config['max_price'] is not None:
                return min(best_bid, self.config['max_price'])
            return best_bid
        except Exception as e:
            logger.error(f"Error getting shadow price: {e}")
            raise
    
    def start(self) -> None:
        """Start the shadow bid strategy."""
        if not self.config['enabled']:
            logger.info("Shadow bid strategy is disabled")
            return
            
        self.is_running = True
        self.last_order_time = 0
        logger.info("Starting shadow bid strategy")
        
        while self.is_running:
            try:
                # Get the price for our shadow bid
                shadow_price = self._get_shadow_price()
                
                # Place or update the order
                self._place_shadow_order(shadow_price)
                
                # Wait for the next refresh
                time.sleep(self.config['refresh_interval'])
                
            except Exception as e:
                logger.error(f"Error in shadow bid strategy: {e}")
                time.sleep(self.config['refresh_interval'])
    
    def stop(self) -> None:
        """Stop the shadow bid strategy."""
        self.is_running = False
        logger.info("Stopping shadow bid strategy")
        
        # Cancel any existing order
        if self.current_order_id is not None:
            try:
                self.api.cancel_order(TRADING_PAIR, self.current_order_id)
                logger.info(f"Cancelled shadow bid order {self.current_order_id}")
            except Exception as e:
                logger.warning(f"Error cancelling order on stop: {e}")
        
        self.current_order_id = None
