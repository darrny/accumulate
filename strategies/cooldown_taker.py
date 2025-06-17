import logging
import time
import random
from typing import Optional
from utils.binance_api import BinanceAPI
from utils.colors import Colors
from config import TRADING_PAIR, COOLDOWN_TAKER, MAX_PRICE, TARGET_QUANTITY
from .base_strategy import BaseStrategy

logger = logging.getLogger(__name__)

class CooldownTakerStrategy(BaseStrategy):
    def __init__(self, api: BinanceAPI):
        super().__init__(api)
        self.config = COOLDOWN_TAKER
        self.last_order_time = 0
        
    def _get_cooldown_time(self) -> float:
        """
        Get cooldown time with jitter.
        """
        base_time = self.config['min_cooldown']
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
        
    def _calculate_order_quantity(self) -> float:
        """
        Calculate the order quantity based on percentage of remaining target.
        """
        remaining = self._get_remaining_quantity()
        if remaining <= 0:
            return 0
            
        # Calculate order size as percentage of remaining target
        order_size = remaining * self.config['order_size_percentage']
        return self.round_quantity(order_size)
        
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
            
        # Check if ask1 quantity is less than our threshold percentage
        max_ask1_qty = remaining * self.config['max_ask1_quantity_percentage']
        if ask_quantity > max_ask1_qty:
            return False
            
        return True
        
    def _place_taker_order(self) -> None:
        """
        Place a taker order.
        """
        try:
            # Get current orderbook
            orderbook = self.api.get_orderbook(TRADING_PAIR, limit=1)
            if not orderbook['asks']:
                return
                
            # Get best ask price and quantity
            best_ask_price = float(orderbook['asks'][0][0])
            best_ask_qty = float(orderbook['asks'][0][1])
            
            # Check if we should place an order
            if not self._should_place_order(best_ask_price, best_ask_qty):
                return
                
            # Calculate order quantity
            quantity = self._calculate_order_quantity()
            if quantity <= 0:
                return
                
            # Round price and quantity
            rounded_price = self.round_price(best_ask_price)
            rounded_qty = self.round_quantity(quantity)
            
            # Place limit order
            order = self.api.place_limit_order(
                pair=TRADING_PAIR,
                price=rounded_price,
                quantity=rounded_qty,
                side='BUY',
                post_only=False  # We want to be a taker
            )
            
            logger.info(f"{Colors.PINK}Placed taker order at {rounded_price} for {rounded_qty} {TRADING_PAIR}{Colors.ENDC}")
            self.last_order_time = time.time()
            
        except Exception as e:
            logger.error(f"{Colors.RED}Error placing taker order: {e}{Colors.ENDC}")
            
    def start(self) -> None:
        """
        Start the strategy.
        """
        logger.info(f"{Colors.PINK}Starting cooldown taker strategy{Colors.ENDC}")
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
                logger.error(f"{Colors.RED}Error in cooldown taker strategy: {e}{Colors.ENDC}")
                time.sleep(1)
                
    def stop(self) -> None:
        """
        Stop the strategy.
        """
        logger.info(f"{Colors.PINK}Stopping cooldown taker strategy{Colors.ENDC}")
        self.running = False
