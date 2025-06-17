import logging
import time
import random
from typing import Optional
from utils.binance_api import BinanceAPI
from utils.colors import Colors
from config import TRADING_PAIR, SHADOW_BID, MAX_PRICE, TARGET_QUANTITY
from .base_strategy import BaseStrategy

logger = logging.getLogger(__name__)

class ShadowBidStrategy(BaseStrategy):
    def __init__(self, api: BinanceAPI):
        super().__init__(api)
        self.config = SHADOW_BID
        self.last_order_time = 0
        self.current_order_id = None
        
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
        
    def _cancel_existing_order(self) -> None:
        """Cancel any existing shadow order."""
        if self.current_order_id:
            try:
                self.api.cancel_order(TRADING_PAIR, self.current_order_id)
                logger.info(f"{Colors.CYAN}Cancelled existing shadow order {self.current_order_id}{Colors.ENDC}")
                self.current_order_id = None
            except Exception as e:
                logger.error(f"{Colors.RED}Error cancelling existing order: {e}{Colors.ENDC}")
        
    def _place_shadow_order(self) -> None:
        """
        Place a shadow order.
        """
        try:
            # Get remaining quantity
            remaining = self._get_remaining_quantity()
            if remaining <= 0:
                return
                
            # Calculate order quantity
            quantity = self._calculate_order_quantity()
            if quantity <= 0:
                return
                
            # Get best bid and ask
            best_bid, best_ask = self.api.get_best_bid_ask(TRADING_PAIR)
            
            # Calculate our price (same as best bid)
            price = self.round_price(best_bid)
            
            # Cancel any existing order
            self._cancel_existing_order()
            
            # Place limit order
            order = self.api.place_limit_order(
                pair=TRADING_PAIR,
                price=price,
                quantity=quantity,
                side='BUY',
                post_only=True
            )
            
            # Store order ID
            self.current_order_id = order['orderId']
            
            logger.info(f"{Colors.CYAN}Placed shadow order at {price} for {quantity} {TRADING_PAIR}{Colors.ENDC}")
            self.last_order_time = time.time()
            
        except Exception as e:
            logger.error(f"{Colors.RED}Error placing shadow order: {e}{Colors.ENDC}")
            
    def start(self) -> None:
        """
        Start the strategy.
        """
        logger.info(f"{Colors.CYAN}Starting shadow bid strategy{Colors.ENDC}")
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
                logger.error(f"{Colors.RED}Error in shadow bid strategy: {e}{Colors.ENDC}")
                time.sleep(1)
                
    def stop(self) -> None:
        """
        Stop the strategy.
        """
        logger.info(f"{Colors.CYAN}Stopping shadow bid strategy{Colors.ENDC}")
        self.running = False
        self._cancel_existing_order()
