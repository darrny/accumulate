import logging
import time
import random
from typing import Optional, Tuple
from utils.binance_api import BinanceAPI
from utils.colors import Colors
from config import TRADING_PAIR, BIG_FISH, MAX_PRICE, TARGET_QUANTITY
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
        
    def _get_remaining_quantity(self) -> float:
        """
        Get the remaining quantity we need to acquire.
        """
        try:
            current_quantity = float(self.api.get_account_balance('BTC').get('free', 0))
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
        
    def _calculate_order_quantity(self, orderbook: dict) -> Tuple[float, float]:
        """
        Calculate the order quantity by summing up quantities until we find a big fish,
        or reach our remaining target quantity.
        
        Returns:
            Tuple of (total_quantity, weighted_average_price)
        """
        total_quantity = 0.0
        total_cost = 0.0
        largest_leg_price = 0.0
        largest_leg_quantity = 0.0
        
        # Get remaining quantity we need to acquire
        remaining_quantity = self._get_remaining_quantity()
        if remaining_quantity <= 0:
            return 0, 0
        
        # Look through asks up to max_orders_to_analyze
        for price, quantity in orderbook['asks'][:self.config['max_orders_to_analyze']]:
            price = float(price)
            quantity = float(quantity)
            
            # Skip if price is too high
            if price > MAX_PRICE:
                break
                
            # Track largest leg
            if quantity > largest_leg_quantity:
                largest_leg_quantity = quantity
                largest_leg_price = price
                
            # Add this order's quantity to our total
            total_quantity += quantity
            total_cost += price * quantity
            
            # If we've found a big fish or reached our remaining target, stop
            min_volume = remaining_quantity * self.config['min_volume_percentage']
            if quantity >= min_volume or total_quantity >= remaining_quantity:
                break
        
        # Cap at remaining quantity
        if total_quantity > remaining_quantity:
            total_quantity = remaining_quantity
            
        # Use the price of the largest leg
        weighted_avg_price = largest_leg_price if largest_leg_quantity > 0 else 0
        
        return total_quantity, weighted_avg_price
        
    def _place_taker_order(self) -> None:
        """
        Place a taker order.
        """
        try:
            # Get current orderbook
            orderbook = self.api.get_orderbook(TRADING_PAIR, limit=self.config['max_orders_to_analyze'])
            if not orderbook['asks']:
                return
                
            # Calculate total quantity and weighted average price
            total_quantity, weighted_avg_price = self._calculate_order_quantity(orderbook)
            
            if total_quantity <= 0:
                return
                
            # Round price and quantity
            rounded_price = self.round_price(weighted_avg_price)
            rounded_qty = self.round_quantity(total_quantity)
            
            # Place limit order
            order = self.api.place_limit_order(
                pair=TRADING_PAIR,
                price=rounded_price,
                quantity=rounded_qty,
                side='BUY',
                post_only=False  # We want to be a taker
            )
            
            # Log orderbook state and order placement in one message
            logger.info(f"\n{Colors.BOLD}=== Big Fish Order ==={Colors.ENDC}")
            logger.info(f"{Colors.BOLD}Top 5 Bids:{Colors.ENDC}")
            for price, qty in orderbook['bids'][:5]:
                logger.info(f"  {float(price):.2f} USDT - {float(qty):.8f} BTC")
            logger.info(f"\n{Colors.BOLD}Top 5 Asks:{Colors.ENDC}")
            for price, qty in orderbook['asks'][:5]:
                logger.info(f"  {float(price):.2f} USDT - {float(qty):.8f} BTC")
            logger.info(f"{Colors.BOLD}============================={Colors.ENDC}")
            logger.info(f"{Colors.GOLDEN}Placed big fish order at {rounded_price} for {rounded_qty} {TRADING_PAIR}{Colors.ENDC}")
            
            self.last_order_time = time.time()
            
        except Exception as e:
            logger.error(f"{Colors.RED}Error placing taker order: {e}{Colors.ENDC}")
            
    def _log_orderbook_state(self) -> None:
        """Log the current orderbook state."""
        try:
            orderbook = self.api.get_orderbook(TRADING_PAIR, limit=5)
            logger.info(f"{Colors.BOLD}Top 5 Bids:{Colors.ENDC}")
            for price, qty in orderbook['bids'][:5]:
                logger.info(f"  {float(price):.2f} USDT - {float(qty):.8f} BTC")
            logger.info(f"\n{Colors.BOLD}Top 5 Asks:{Colors.ENDC}")
            for price, qty in orderbook['asks'][:5]:
                logger.info(f"  {float(price):.2f} USDT - {float(qty):.8f} BTC")
            logger.info(f"{Colors.BOLD}============================={Colors.ENDC}")
        except Exception as e:
            logger.error(f"{Colors.RED}Error logging orderbook state: {e}{Colors.ENDC}")
        
    def start(self) -> None:
        """
        Start the strategy.
        """
        logger.info(f"{Colors.GOLDEN}Starting big fish strategy{Colors.ENDC}")
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
