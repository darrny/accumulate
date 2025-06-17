import logging
import time
import sys
import json
import uuid
import threading
import importlib.util
import os
from typing import Dict, Optional
from binance.client import Client
from binance import ThreadedWebsocketManager
from binance import AsyncClient, BinanceSocketManager
from utils.binance_api import BinanceAPI
from utils.ed25519_auth import get_user_data_stream, close_user_data_stream
from utils.colors import Colors, STRATEGY_COLORS
from config import TRADING_PAIR, SHADOW_BID, COOLDOWN_TAKER, BIG_FISH, TARGET_QUANTITY, BINANCE_API_KEY, BINANCE_API_SECRET, USE_TESTNET
from strategies.shadow_bid import ShadowBidStrategy
from strategies.cooldown_taker import CooldownTakerStrategy
from strategies.big_fish import BigFishStrategy

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def load_strategy_config():
    """Load strategy configuration from StrategyConfig.py"""
    try:
        spec = importlib.util.spec_from_file_location("strategy_config", "StrategyConfig.py")
        if spec is None or spec.loader is None:
            raise ImportError("Could not load StrategyConfig.py")
        strategy_config = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(strategy_config)
        return strategy_config
    except Exception as e:
        logger.error(f"{Colors.RED}Error loading strategy config: {e}{Colors.ENDC}")
        return None

class TradingMonitor:
    def __init__(self, api: BinanceAPI):
        self.api = api
        self.strategies = {}
        self.strategy_threads = {}  # Store strategy threads
        self.orderbook = {'bids': [], 'asks': []}
        self.last_trade = None
        self.running = False
        self.target_quantity = TARGET_QUANTITY
        self.twm = None
        self.conn_key = None
        self.user_stream = None
        self.last_config_check = 0
        self.config_check_interval = 10  # Check config every 10 seconds
        
        # Track weighted average price
        self.total_cost = 0.0
        self.filled_quantity = 0.0  # Track quantity from filled orders
        self.weighted_avg_price = 0.0
        
        # Initialize strategies based on initial config
        self._update_strategies()
        
    def _update_strategies(self) -> None:
        """Update strategies based on current configuration"""
        try:
            # Load current strategy config
            config = load_strategy_config()
            if config is None:
                return
                
            # Check each strategy
            for name, strategy_class, config_dict in [
                ('shadow_bid', ShadowBidStrategy, SHADOW_BID),
                ('cooldown_taker', CooldownTakerStrategy, COOLDOWN_TAKER),
                ('big_fish', BigFishStrategy, BIG_FISH)
            ]:
                should_be_running = getattr(config, name.upper(), False)
                is_running = name in self.strategies
                
                # If strategy should be running but isn't
                if should_be_running and not is_running:
                    logger.info(f"{Colors.BOLD}Initializing {name} strategy...{Colors.ENDC}")
                    self.strategies[name] = strategy_class(self.api, monitor=self)
                    if self.running:  # Only start if monitor is running
                        self._start_strategy(name)
                        
                # If strategy shouldn't be running but is
                elif not should_be_running and is_running:
                    logger.info(f"{Colors.BOLD}Stopping {name} strategy...{Colors.ENDC}")
                    self._stop_strategy(name)
                    del self.strategies[name]
                    
        except Exception as e:
            logger.error(f"{Colors.RED}Error updating strategies: {e}{Colors.ENDC}")
            
    def _start_strategy(self, name: str) -> None:
        """Start a strategy in its own thread"""
        try:
            color = STRATEGY_COLORS.get(name, Colors.ENDC)
            logger.info(f"{color}Starting {name} strategy thread...{Colors.ENDC}")
            thread = threading.Thread(target=self.strategies[name].start, name=f"{name}_thread")
            thread.daemon = True
            thread.start()
            self.strategy_threads[name] = thread
            logger.info(f"{color}{name} strategy thread started successfully{Colors.ENDC}")
        except Exception as e:
            logger.error(f"{Colors.RED}Failed to start {name} strategy thread: {str(e)}{Colors.ENDC}")
            
    def _stop_strategy(self, name: str) -> None:
        """Stop a strategy and its thread"""
        try:
            color = STRATEGY_COLORS.get(name, Colors.ENDC)
            logger.info(f"{color}Stopping {name} strategy...{Colors.ENDC}")
            self.strategies[name].stop()
            
            # Wait for thread to finish
            if name in self.strategy_threads:
                thread = self.strategy_threads[name]
                if thread.is_alive():
                    thread.join(timeout=5)
                del self.strategy_threads[name]
                
            logger.info(f"{color}{name} strategy stopped successfully{Colors.ENDC}")
        except Exception as e:
            logger.error(f"{Colors.RED}Failed to stop {name} strategy: {str(e)}{Colors.ENDC}")
            
    def _get_current_quantity(self) -> float:
        """Get current quantity of the base asset (e.g., BTC)."""
        try:
            base_asset = TRADING_PAIR.replace('USDT', '')
            balance = self.api.get_account_balance(base_asset)
            if isinstance(balance, dict):
                return float(balance['free']) + float(balance['locked'])
            elif isinstance(balance, (int, float)):
                return float(balance)
            return 0.0
        except Exception as e:
            logger.error(f"Error getting current quantity: {e}")
            return 0.0
            
    def _check_target_reached(self) -> bool:
        """Check if we've reached our target quantity."""
        current_quantity = self._get_current_quantity()
        remaining = self.target_quantity - current_quantity
        
        # Calculate remaining cost based on weighted average price
        remaining_cost = remaining * self.weighted_avg_price if self.weighted_avg_price > 0 else 0
        
        logger.info(f"{Colors.BOLD}{Colors.MAGENTA}Progress: {current_quantity:.8f} / {self.target_quantity:.8f} BTC (Remaining: {remaining:.8f} BTC){Colors.ENDC}")
        logger.info(f"{Colors.BOLD}{Colors.MAGENTA}Average Entry: {self.weighted_avg_price:.2f} USDT (Remaining Cost: {remaining_cost:.2f} USDT){Colors.ENDC}")
        
        return current_quantity >= self.target_quantity
            
    def _handle_orderbook_update(self, msg: Dict) -> None:
        """Handle orderbook update from WebSocket."""
        try:
            # Update orderbook
            self.orderbook['bids'] = [(float(price), float(qty)) for price, qty in msg['b']]
            self.orderbook['asks'] = [(float(price), float(qty)) for price, qty in msg['a']]
        except Exception as e:
            logger.error(f"Error handling orderbook update: {e}")

    def _log_orderbook_state(self) -> None:
        """Log the current orderbook state."""
        if self.orderbook['bids'] and self.orderbook['asks']:
            logger.info(f"\n{Colors.BOLD}=== Current Orderbook State ==={Colors.ENDC}")
            logger.info(f"{Colors.BOLD}Top 5 Bids:{Colors.ENDC}")
            for price, qty in self.orderbook['bids'][:5]:
                logger.info(f"  {price:.2f} USDT - {qty:.8f} BTC")
            logger.info(f"\n{Colors.BOLD}Top 5 Asks:{Colors.ENDC}")
            for price, qty in self.orderbook['asks'][:5]:
                logger.info(f"  {price:.2f} USDT - {qty:.8f} BTC")
            logger.info(f"{Colors.BOLD}============================={Colors.ENDC}")
            
    def _handle_trade_update(self, msg: Dict) -> None:
        """Handle trade update from WebSocket."""
        try:
            # Update last trade
            self.last_trade = {
                'price': float(msg['p']),
                'quantity': float(msg['q']),
                'time': msg['T'],
                'is_buyer_maker': msg['m']
            }
            
            # Check if we've reached target
            if self._check_target_reached():
                logger.info(f"{Colors.BOLD}{Colors.GREEN}Target quantity reached! Stopping all strategies...{Colors.ENDC}")
                self.stop()
                sys.exit(0)
                
        except Exception as e:
            logger.error(f"Error handling trade update: {e}")
            
    def _handle_balance_update(self, msg: Dict) -> None:
        """Handle balance update from WebSocket."""
        try:
            # Extract the event data from the message
            event = msg.get('event', {})
            
            # Handle execution report
            if event.get('e') == 'executionReport':
                # Check for insufficient funds error
                if event.get('X') == 'REJECTED' and 'insufficient balance' in event.get('r', '').lower():
                    logger.error(f"{Colors.RED}Insufficient funds error detected. Stopping all strategies...{Colors.ENDC}")
                    self._handle_insufficient_funds()
                    return
                
                # Update weighted average price for filled buy orders
                if event['X'] == 'FILLED' and event['S'] == 'BUY':
                    quantity = float(event['q'])
                    price = float(event['p'])
                    cost = quantity * price
                    
                    # Update total cost and filled quantity
                    self.total_cost += cost
                    self.filled_quantity += quantity
                    
                    # Calculate weighted average price using filled quantity
                    if self.filled_quantity > 0:
                        self.weighted_avg_price = self.total_cost / self.filled_quantity
                
                # Log the execution report with strategy color
                strategy = event.get('c', '').split('_')[0]  # Extract strategy name from client order ID
                color = STRATEGY_COLORS.get(strategy, Colors.ENDC)
                logger.info(f"{color}Order Update - {event['S']} {event['q']} @ {event['p']} - Status: {event['X']}{Colors.ENDC}")
                
            # Handle balance update
            elif event.get('e') == 'outboundAccountPosition':
                # Log each balance update
                for balance in event.get('B', []):
                    asset = balance.get('a')
                    free = float(balance.get('f', 0))
                    locked = float(balance.get('l', 0))
                    
                    if free > 0 or locked > 0:
                        logger.info(f"{Colors.BLUE}Balance Update - {asset}: Free={free:.8f}, Locked={locked:.8f}{Colors.ENDC}")
            
            # Check if we've reached target
            if self._check_target_reached():
                logger.info(f"{Colors.BOLD}{Colors.GREEN}Target quantity reached! Stopping all strategies...{Colors.ENDC}")
                self.stop()
                sys.exit(0)
                
        except Exception as e:
            logger.error(f"{Colors.RED}Error handling balance update: {e}{Colors.ENDC}")
            
    def _handle_insufficient_funds(self) -> None:
        """Handle insufficient funds error by stopping all strategies and canceling orders."""
        try:
            # Cancel all open orders
            open_orders = self.api.get_open_orders(TRADING_PAIR)
            for order in open_orders:
                try:
                    self.api.cancel_order(TRADING_PAIR, order['orderId'])
                    logger.info(f"{Colors.YELLOW}Cancelled order {order['orderId']}{Colors.ENDC}")
                except Exception as e:
                    logger.error(f"{Colors.RED}Error cancelling order {order['orderId']}: {e}{Colors.ENDC}")
            
            # Stop all strategies
            for name, strategy in self.strategies.items():
                color = STRATEGY_COLORS.get(name, Colors.ENDC)
                logger.info(f"{color}Stopping {name} strategy due to insufficient funds...{Colors.ENDC}")
                strategy.stop()
            
            # Stop the monitor
            self.stop()
            sys.exit(1)
            
        except Exception as e:
            logger.error(f"{Colors.RED}Error handling insufficient funds: {e}{Colors.ENDC}")
            sys.exit(1)
            
    def start(self) -> None:
        """Start monitoring with WebSocket."""
        logger.info(f"{Colors.BOLD}Starting trading monitor...{Colors.ENDC}")
        self.running = True
        
        try:
            # Initialize WebSocket manager with API client
            logger.info(f"{Colors.BOLD}Initializing WebSocket manager...{Colors.ENDC}")
            
            # Configure WebSocket manager based on testnet setting
            if USE_TESTNET:
                # For testnet, use the testnet configuration
                self.twm = ThreadedWebsocketManager(
                    api_key=BINANCE_API_KEY,
                    api_secret=BINANCE_API_SECRET,
                    tld='us'  # Use 'us' for testnet
                )
            else:
                # For production, use default settings
                self.twm = ThreadedWebsocketManager(
                    api_key=BINANCE_API_KEY,
                    api_secret=BINANCE_API_SECRET
                )
            
            if not self.twm:
                raise Exception("Failed to initialize WebSocket manager")
            
            # start is required to initialise its internal loop
            logger.info(f"{Colors.BOLD}Starting WebSocket manager...{Colors.ENDC}")
            self.twm.start()
            
            # Start WebSocket streams
            logger.info(f"{Colors.BOLD}Starting depth socket...{Colors.ENDC}")
            self.conn_key = self.twm.start_depth_socket(
                symbol=TRADING_PAIR.lower(),
                callback=self._handle_orderbook_update
            )
            
            logger.info(f"{Colors.BOLD}Starting trade socket...{Colors.ENDC}")
            self.twm.start_trade_socket(
                symbol=TRADING_PAIR.lower(),
                callback=self._handle_trade_update
            )
            
            # Try to start user data stream if API keys are valid
            try:
                logger.info(f"{Colors.BOLD}Attempting to start user data stream...{Colors.ENDC}")
                
                if USE_TESTNET:
                    # Use ED25519 authentication for testnet
                    self.user_stream = get_user_data_stream(self._handle_balance_update)
                    logger.info(f"{Colors.GREEN}User data stream started successfully with ED25519 authentication{Colors.ENDC}")
                else:
                    # Use regular authentication for production
                    self.user_stream = self.twm.start_user_socket(
                        callback=self._handle_balance_update
                    )
                    logger.info(f"{Colors.GREEN}User data stream started successfully{Colors.ENDC}")
                
            except Exception as e:
                logger.error(f"{Colors.RED}Failed to start user data stream: {str(e)}{Colors.ENDC}")
                logger.error(f"{Colors.RED}This might be due to invalid API keys or insufficient permissions{Colors.ENDC}")
                logger.info(f"{Colors.YELLOW}Continuing without user data stream...{Colors.ENDC}")
            
            # Start initial strategies
            for name in self.strategies:
                self._start_strategy(name)
            
            # Keep the main thread alive
            while self.running:
                # Check if it's time to reload strategy config
                current_time = time.time()
                if current_time - self.last_config_check >= self.config_check_interval:
                    self._update_strategies()
                    self.last_config_check = current_time
                    
                # Check if any strategy threads have died
                for name, thread in list(self.strategy_threads.items()):
                    if not thread.is_alive():
                        logger.error(f"{Colors.RED}{name} strategy thread died unexpectedly{Colors.ENDC}")
                        # Restart the thread if the strategy is still enabled
                        if name in self.strategies:
                            self._start_strategy(name)
                            
                time.sleep(1)
                
        except KeyboardInterrupt:
            logger.info(f"{Colors.YELLOW}Stopping monitor...{Colors.ENDC}")
        except Exception as e:
            logger.error(f"{Colors.RED}Error in monitor: {str(e)}{Colors.ENDC}")
            logger.error(f"{Colors.RED}Stack trace:", exc_info=True)
        finally:
            self.stop()
            
    def stop(self) -> None:
        """Stop monitoring and clean up."""
        logger.info(f"{Colors.YELLOW}Stopping monitor...{Colors.ENDC}")
        self.running = False
        
        # Stop all strategies
        for name in list(self.strategies.keys()):
            self._stop_strategy(name)
            
        # Stop WebSocket connections if they were initialized
        if self.twm is not None:
            try:
                # Close the user data stream if we have one
                if self.user_stream:
                    if USE_TESTNET:
                        close_user_data_stream(self.user_stream)
                    else:
                        self.twm.stop_socket(self.user_stream)
                
                self.twm.stop()
                logger.info(f"{Colors.GREEN}WebSocket connections closed{Colors.ENDC}")
            except Exception as e:
                logger.error(f"{Colors.RED}Error stopping WebSocket connections: {e}{Colors.ENDC}")
        else:
            logger.info(f"{Colors.YELLOW}No WebSocket connections to close{Colors.ENDC}")

def main():
    """Main entry point."""
    try:
        # Initialize API client
        api = BinanceAPI(
            api_key=BINANCE_API_KEY,
            api_secret=BINANCE_API_SECRET,
            use_testnet=USE_TESTNET
        )
        
        # Create and start monitor
        monitor = TradingMonitor(api)
        monitor.start()
        
    except Exception as e:
        logger.error(f"{Colors.RED}Error in main: {e}{Colors.ENDC}")
        raise

if __name__ == "__main__":
    main()