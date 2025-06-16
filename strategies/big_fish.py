import logging
import time
import random
from typing import List, Optional, Tuple
from utils.binance_api import BinanceAPI
from config import TRADING_PAIR, BIG_FISH
from .base_strategy import BaseStrategy

logger = logging.getLogger(__name__)

class BigFishStrategy(BaseStrategy):
    def __init__(self, api: BinanceAPI):
        super().__init__(api)
        self.config = BIG_FISH
        self.last_order_time = 0
        
    def _get_cooldown_time(self) -> float:
        """
        Get cooldown time with jitter.
        """
        base_time = self.config['cooldown_time']
        jitter = self.config['jitter']
        return base_time + random.uniform(-jitter, jitter)
        
    def _calculate_weighted_price(self, orders: List[Tuple[float, float]]) -> float:
        """
        Calculate weighted average price from a list of orders.
        """
        total_quantity = sum(qty for _, qty in orders)
        if total_quantity == 0:
            return 0
            
        weighted_sum = sum(price * qty for price, qty in orders)
        return weighted_sum / total_quantity
        
    def _find_big_fish(self) -> Optional[Tuple[float, float, List[Tuple[float, float]]]]:
        """
        Find a big fish in the orderbook.
        Returns tuple of (price, quantity, orders) if found, None otherwise.
        """
        try:
            # Get orderbook
            orderbook = self.api.get_orderbook(TRADING_PAIR, limit=self.config['max_orders_to_analyze'])
            
            # Look through asks for a big fish
            for price, quantity in orderbook['asks']:
                price = float(price)
                quantity = float(quantity)
                
                # Check if this individual order is a big fish
                if quantity >= self.config['min_volume']:
                    # Calculate weighted average price for all orders up to and including this one
                    orders = []
                    total_quantity = 0
                    
                    for ask_price, ask_qty in orderbook['asks']:
                        ask_price = float(ask_price)
                        ask_qty = float(ask_qty)
                        
                        orders.append((ask_price, ask_qty))
                        total_quantity += ask_qty
                        
                        # Stop when we reach our big fish
                        if ask_price == price:
                            break
                    
                    # Check if weighted average price is acceptable
                    avg_price = self._calculate_weighted_price(orders)
                    if self.config['max_price'] is None or avg_price <= self.config['max_price']:
                        return price, total_quantity, orders
                    
            return None
            
        except Exception as e:
            logger.error(f"Error finding big fish: {e}")
            return None
            
    def _place_big_fish_order(self) -> None:
        """
        Place an order to take a big fish.
        """
        try:
            # Find a big fish
            result = self._find_big_fish()
            if result is None:
                return
                
            price, total_quantity, orders = result
            
            # Round price and quantity
            rounded_price = self.round_price(price)
            rounded_quantity = self.round_quantity(total_quantity)
            
            # Log orderbook state before taking the order
            logger.info("\n=== Before Taking Big Fish Order ===")
            orderbook = self.api.get_orderbook(TRADING_PAIR, limit=self.config['max_orders_to_analyze'])
            
            logger.info("Top Bids:")
            for bid_price, bid_qty in orderbook['bids'][:5]:
                logger.info(f"  Price: {float(bid_price):.2f}, Quantity: {float(bid_qty):.4f}")
                
            logger.info("\nTop Asks (up to big fish):")
            for ask_price, ask_qty in orderbook['asks'][:len(orders)]:
                logger.info(f"  Price: {float(ask_price):.2f}, Quantity: {float(ask_qty):.4f}")
            
            # Place limit order with rounded values
            order = self.api.place_limit_order(
                pair=TRADING_PAIR,
                price=rounded_price,
                quantity=rounded_quantity,
                side='BUY',
                post_only=False  # We want to take liquidity
            )
            
            # Wait a moment for the order to be processed
            time.sleep(1)
            
            # Log orderbook state after taking the order
            logger.info("\n=== After Taking Big Fish Order ===")
            orderbook = self.api.get_orderbook(TRADING_PAIR, limit=self.config['max_orders_to_analyze'])
            
            logger.info("Top Bids:")
            for bid_price, bid_qty in orderbook['bids'][:5]:
                logger.info(f"  Price: {float(bid_price):.2f}, Quantity: {float(bid_qty):.4f}")
                
            logger.info("\nTop Asks:")
            for ask_price, ask_qty in orderbook['asks'][:5]:
                logger.info(f"  Price: {float(ask_price):.2f}, Quantity: {float(ask_qty):.4f}")
            
            logger.info(f"\nOrder Details:")
            logger.info(f"  Original Price: {price:.2f}")
            logger.info(f"  Rounded Price: {rounded_price:.2f}")
            logger.info(f"  Original Quantity: {total_quantity:.4f}")
            logger.info(f"  Rounded Quantity: {rounded_quantity:.4f}")
            logger.info(f"  Orders Taken: {len(orders)}")
            logger.info(f"  Average Price: {self._calculate_weighted_price(orders):.2f}")
            logger.info("===============================\n")
            
            self.last_order_time = time.time()
            
        except Exception as e:
            logger.error(f"Error placing big fish order: {e}")
            
    def start(self) -> None:
        """
        Start the strategy.
        """
        logger.info("Starting big fish strategy")
        self.running = True
        
        while self.running:
            try:
                # Check if we're in cooldown
                if time.time() - self.last_order_time < self._get_cooldown_time():
                    time.sleep(1)
                    continue
                    
                # Try to place an order
                self._place_big_fish_order()
                
                # Sleep to avoid hitting rate limits
                time.sleep(1)
                
            except Exception as e:
                logger.error(f"Error in big fish strategy: {e}")
                time.sleep(1)
                
    def stop(self) -> None:
        """
        Stop the strategy.
        """
        logger.info("Stopping big fish strategy")
        self.running = False
