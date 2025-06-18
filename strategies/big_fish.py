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
        """Calculate the quantity for our big fish order."""
        try:
            # Get remaining quantity to acquire
            remaining = self.get_remaining_quantity()
            if remaining <= 0:
                return 0.0

            # Look through asks to find a big fish
            total_quantity = 0
            weighted_price = 0
            min_volume = self.target_quantity * self.config['min_volume_percentage']
            
            for price, quantity in orderbook['asks']:
                price = float(price)
                quantity = float(quantity)
                
                # Add this order to our running totals
                total_quantity += quantity
                weighted_price = ((weighted_price * (total_quantity - quantity)) + (price * quantity)) / total_quantity
                
                # Check if we found a big fish
                if quantity >= min_volume and weighted_price <= MAX_PRICE:
                    # Found a big fish! Take all orders up to and including this one
                    return min(remaining, total_quantity)
                
                # Stop if we've looked at enough orders
                if len(orderbook['asks']) > self.config['max_orders_to_analyze']:
                    break
            
            return 0.0  # No big fish found
            
        except Exception as e:
            logger.error(f"{Colors.RED}Error calculating order quantity: {str(e)}{Colors.ENDC}")
            return 0.0

    def _calculate_order_price(self, orderbook: Dict) -> float:
        """Calculate the price for our big fish order."""
        try:
            # Look through asks to find a big fish
            total_quantity = 0
            weighted_price = 0
            min_volume = self.target_quantity * self.config['min_volume_percentage']
            
            for price, quantity in orderbook['asks']:
                price = float(price)
                quantity = float(quantity)
                
                # Add this order to our running totals
                total_quantity += quantity
                weighted_price = ((weighted_price * (total_quantity - quantity)) + (price * quantity)) / total_quantity
                
                # Check if we found a big fish
                if quantity >= min_volume and weighted_price <= MAX_PRICE:
                    # Found a big fish! Use this order's price
                    return price
                
                # Stop if we've looked at enough orders
                if len(orderbook['asks']) > self.config['max_orders_to_analyze']:
                    break
            
            return 0.0  # No big fish found
            
        except Exception as e:
            logger.error(f"{Colors.RED}Error calculating order price: {str(e)}{Colors.ENDC}")
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
                
            # Calculate order price (use the price of the big ask)
            price = self._calculate_order_price(orderbook)
            if price <= 0:
                return
                
            # Place limit order
            order = self.api.place_limit_order(
                pair=TRADING_PAIR,
                price=price,
                quantity=quantity,
                side='BUY'
            )
            
            # Update acquired quantity if in standalone mode
            if self.monitor is None:
                self.update_acquired_quantity(quantity)
            
            logger.info(f"{Colors.PINK}Placed limit order for {quantity} {BASE} at {price} {QUOTE}{Colors.ENDC}")
            
            self.last_order_time = time.time()
            
            # Update progress
            self._update_progress()
            
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
