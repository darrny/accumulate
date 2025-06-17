import logging
import time
import random
from typing import Optional, Tuple
from utils.binance_api import BinanceAPI
from config import TRADING_PAIR, SHADOW_BID, MAX_PRICE
from .base_strategy import BaseStrategy

logger = logging.getLogger(__name__)

class ShadowBidStrategy(BaseStrategy):
    def __init__(self, api: BinanceAPI):
        super().__init__(api)
        self.config = SHADOW_BID
        self.last_order_time = 0
        
    def _get_cooldown_time(self) -> float:
        """
        Get cooldown time with jitter.
        """
        base_time = self.config['cooldown_time']
        jitter = self.config['jitter']
        return base_time + random.uniform(-jitter, jitter)
        
    def _place_shadow_order(self) -> None:
        """
        Place a shadow order.
        """
        try:
            # Get current best bid
            orderbook = self.api.get_orderbook(TRADING_PAIR, limit=1)
            if not orderbook['bids']:
                return
                
            best_bid_price = float(orderbook['bids'][0][0])
            best_bid_qty = float(orderbook['bids'][0][1])
            
            # Calculate shadow price
            shadow_price = best_bid_price * (1 - self.config['price_multiplier'])
            
            # Check if price is within our limit
            if shadow_price > MAX_PRICE:
                return
                
            # Calculate order quantity
            order_qty = self._calculate_order_quantity(best_bid_qty)
            
            # Round price and quantity
            rounded_price = self.round_price(shadow_price)
            rounded_qty = self.round_quantity(order_qty)
            
            # Place limit order
            order = self.api.place_limit_order(
                pair=TRADING_PAIR,
                price=rounded_price,
                quantity=rounded_qty,
                side='BUY',
                post_only=True  # We want to be a maker
            )
            
            logger.info(f"Placed shadow order at {rounded_price} for {rounded_qty} {TRADING_PAIR}")
            self.last_order_time = time.time()
            
        except Exception as e:
            logger.error(f"Error placing shadow order: {e}")
            
    def _calculate_order_quantity(self, best_bid_qty: float) -> float:
        """
        Calculate the order quantity based on the best bid quantity.
        """
        # Calculate quantity based on multiplier
        quantity = best_bid_qty * self.config['quantity_multiplier']
        
        # Cap at maximum order quantity
        quantity = min(quantity, self.config['max_order_quantity'])
        
        # Ensure quantity is properly formatted (no scientific notation)
        quantity = float(f"{quantity:.8f}")
        
        return quantity
        
    def start(self) -> None:
        """
        Start the strategy.
        """
        logger.info("Starting shadow bid strategy")
        self.running = True
        
        while self.running:
            try:
                # Check if we're in cooldown
                if time.time() - self.last_order_time < self._get_cooldown_time():
                    time.sleep(1)
                    continue
                    
                # Try to place an order
                self._place_shadow_order()
                
                # Sleep to avoid hitting rate limits
                time.sleep(1)
                
            except Exception as e:
                logger.error(f"Error in shadow bid strategy: {e}")
                time.sleep(1)
                
    def stop(self) -> None:
        """
        Stop the strategy.
        """
        logger.info("Stopping shadow bid strategy")
        self.running = False
