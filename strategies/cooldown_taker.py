import logging
import time
import random
from typing import Optional, Tuple
from utils.binance_api import BinanceAPI
from config import TRADING_PAIR, COOLDOWN_TAKER
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
        base_time = self.config['cooldown_time']
        jitter = self.config['jitter']
        return base_time + random.uniform(-jitter, jitter)
        
    def _should_place_order(self, ask_price: float, ask_quantity: float) -> bool:
        """
        Check if we should place an order based on price and quantity.
        """
        # Check if price is within our limit
        if self.config['max_price'] is not None and ask_price > self.config['max_price']:
            return False
            
        # Check if quantity is below our maximum
        if ask_quantity > self.config['max_ask_quantity']:
            return False
            
        return True
        
    def _calculate_order_quantity(self, ask_quantity: float) -> float:
        """
        Calculate the order quantity based on the ask quantity.
        """
        # Calculate quantity based on multiplier
        quantity = ask_quantity * self.config['order_multiplier']
        
        # Cap at maximum order quantity
        if self.config['max_order_quantity'] is not None:
            quantity = min(quantity, self.config['max_order_quantity'])
            
        return quantity
        
    def _place_taker_order(self) -> None:
        """
        Place a taker order.
        """
        try:
            # Get current best ask
            orderbook = self.api.get_orderbook(TRADING_PAIR, limit=1)
            if not orderbook['asks']:
                return
                
            ask_price = float(orderbook['asks'][0][0])
            ask_quantity = float(orderbook['asks'][0][1])
            
            # Check if we should place an order
            if not self._should_place_order(ask_price, ask_quantity):
                return
                
            # Calculate order quantity
            order_qty = self._calculate_order_quantity(ask_quantity)
            
            # Round price and quantity
            rounded_price = self.round_price(ask_price)
            rounded_qty = self.round_quantity(order_qty)
            
            # Place limit order
            order = self.api.place_limit_order(
                pair=TRADING_PAIR,
                price=rounded_price,
                quantity=rounded_qty,
                side='BUY',
                post_only=False  # We want to be a taker
            )
            
            logger.info(f"Placed taker order at {rounded_price} for {rounded_qty} {TRADING_PAIR}")
            self.last_order_time = time.time()
            
        except Exception as e:
            logger.error(f"Error placing taker order: {e}")
            
    def start(self) -> None:
        """
        Start the strategy.
        """
        logger.info("Starting cooldown taker strategy")
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
                logger.error(f"Error in cooldown taker strategy: {e}")
                time.sleep(1)
                
    def stop(self) -> None:
        """
        Stop the strategy.
        """
        logger.info("Stopping cooldown taker strategy")
        self.running = False
