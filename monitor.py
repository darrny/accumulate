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
from utils.colors import Colors, STRATEGY_COLORS
from config import TRADING_PAIR, SHADOW_BID, COOLDOWN_TAKER, BIG_FISH, TARGET_QUANTITY, BINANCE_API_KEY, BINANCE_API_SECRET, USE_TESTNET, BASE, QUOTE, QUOTE_PRICE
from strategies.shadow_bid import ShadowBidStrategy
from strategies.cooldown_taker import CooldownTakerStrategy
from strategies.big_fish import BigFishStrategy
from datetime import datetime
import traceback
import signal
import importlib

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
    def __init__(self):
        """Initialize the trading monitor."""
        self.api = BinanceAPI(api_key=BINANCE_API_KEY, api_secret=BINANCE_API_SECRET)
        self.strategies = {}
        self.running = False
        self.ws_manager = None
        self.user_stream = None
        self.strategy_threads = {}
        self._shutdown_in_progress = False  # Initialize shutdown flag
        
        # Trading pair configuration
        self.base = BASE
        self.quote = QUOTE
        self.target_quantity = TARGET_QUANTITY
        
        # Initialize session tracking
        self._session_start_quantity = 0.0
        self._session_acquired_quantity = 0.0
        self._session_total_cost = 0.0
        self._session_average_price = 0.0
        self._session_trades = []  # Track trades in this session
        
        # Initialize orderbook
        self.orderbook = {'bids': [], 'asks': []}
        
        # Get initial balance before starting strategies
        try:
            initial_balance = self.api.get_account_balance(BASE)
            if isinstance(initial_balance, dict):
                self._session_start_quantity = float(initial_balance.get('free', 0))
            else:
                self._session_start_quantity = float(initial_balance)
            logger.info(f"Initial {BASE} balance: {self._session_start_quantity}")
        except Exception as e:
            logger.error(f"Error getting initial balance: {e}")
            self._session_start_quantity = 0.0

    def start(self) -> None:
        """Start the trading monitor."""
        try:
            logger.info("Starting trading monitor...")
            
            # Initialize WebSocket manager
            logger.info("Initializing WebSocket manager...")
            self.ws_manager = ThreadedWebsocketManager(
                api_key=BINANCE_API_KEY,
                api_secret=BINANCE_API_SECRET
            )
            
            # Start WebSocket manager
            logger.info("Starting WebSocket manager...")
            self.ws_manager.start()
            
            # Start depth socket
            logger.info("Starting depth socket...")
            self.ws_manager.start_depth_socket(
                symbol=TRADING_PAIR,
                callback=self._handle_orderbook_update
            )
            
            # Start trade socket
            logger.info("Starting trade socket...")
            self.ws_manager.start_trade_socket(
                symbol=TRADING_PAIR,
                callback=self._handle_trade_update
            )
            
            # Start user data stream
            logger.info("Starting user data stream...")
            self.user_stream = self.ws_manager.start_user_socket(
                callback=self._handle_user_update
            )
            logger.info("User data stream started successfully")

            # --- Load strategy config before initializing strategies ---
            strategy_config = None
            try:
                spec = importlib.util.spec_from_file_location("config_strategies", "config_strategies.py")
                if spec is not None and spec.loader is not None:
                    strategy_config = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(strategy_config)
            except Exception as e:
                logger.error(f"{Colors.RED}Error loading config_strategies.py: {e}{Colors.ENDC}")
                strategy_config = None

            # Only initialize strategies that are enabled in config
            strategies_to_init = []
            if strategy_config is not None:
                if getattr(strategy_config, 'SHADOW_BID', False):
                    strategies_to_init.append(('shadow_bid', ShadowBidStrategy))
                if getattr(strategy_config, 'COOLDOWN_TAKER', False):
                    strategies_to_init.append(('cooldown_taker', CooldownTakerStrategy))
                if getattr(strategy_config, 'BIG_FISH', False):
                    strategies_to_init.append(('big_fish', BigFishStrategy))
            else:
                # If config can't be loaded, default to all enabled (fail-safe)
                strategies_to_init = [
                    ('shadow_bid', ShadowBidStrategy),
                    ('cooldown_taker', CooldownTakerStrategy),
                    ('big_fish', BigFishStrategy)
                ]

            # Initialize and start enabled strategies with 4-second intervals
            for i, (name, cls) in enumerate(strategies_to_init):
                logger.info(f"Initializing {name} strategy...")
                self.strategies[name] = cls(self.api, self)
                logger.info(f"Starting {name} strategy thread...")
                thread = threading.Thread(target=self.strategies[name].start)
                thread.daemon = True
                thread.start()
                self.strategy_threads[name] = thread
                logger.info(f"{name} strategy thread started successfully")
                if i < len(strategies_to_init) - 1:
                    logger.info(f"Waiting 4 seconds before starting next strategy...")
                    time.sleep(4)

            # Set running flag
            self.running = True
            
            # Start strategy config watcher thread
            watcher_thread = threading.Thread(target=self._strategy_config_watcher)
            watcher_thread.daemon = True
            watcher_thread.start()
            
            # Keep main thread alive and check for target reached
            while self.running:
                # Check if target has been reached
                if self._check_target_reached():
                    logger.info(f"{Colors.GREEN}Target reached in main loop! Shutting down...{Colors.ENDC}")
                    self.stop()
                    break
                time.sleep(1)
                
        except Exception as e:
            logger.error(f"Error starting monitor: {e}")
            self.stop()
            raise

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
        """Get current quantity including both free and locked amounts."""
        try:
            # Get current balance
            balance = self.api.get_account_balance(self.base)
            if isinstance(balance, dict):
                free = float(balance.get('free', 0))
                locked = float(balance.get('locked', 0))
                return free + locked
                return float(balance)
        except Exception as e:
            logger.error(f"Error getting current quantity: {e}")
            return 0
            
    def _check_target_reached(self) -> bool:
        """Check if we've reached our target quantity."""
        try:
            # Get current balance
            current_balance = self.api.get_account_balance(self.base)
            if isinstance(current_balance, dict):
                current_quantity = float(current_balance.get('free', 0))
                locked_quantity = float(current_balance.get('locked', 0))
            else:
                current_quantity = float(current_balance)
                locked_quantity = 0.0
                
            # Calculate session acquired amount
            session_acquired = current_quantity - self._session_start_quantity

            return session_acquired >= self.target_quantity
            
        except Exception as e:
            logger.error(f"Error checking target reached: {e}")
            return False
            
    def _handle_orderbook_update(self, msg: Dict) -> None:
        """Handle orderbook updates from WebSocket."""
        try:
            if msg['e'] == 'depthUpdate' and msg['s'] == TRADING_PAIR:
                # Update bids
                for bid in msg['b']:
                    price, qty = float(bid[0]), float(bid[1])
                    if qty == 0:
                        self.orderbook['bids'] = [b for b in self.orderbook['bids'] if float(b[0]) != price]
                    else:
                        # Update or insert bid
                        updated = False
                        for i, b in enumerate(self.orderbook['bids']):
                            if float(b[0]) == price:
                                self.orderbook['bids'][i] = [bid[0], bid[1]]
                                updated = True
                                break
                        if not updated:
                            self.orderbook['bids'].append([bid[0], bid[1]])
                
                # Update asks
                for ask in msg['a']:
                    price, qty = float(ask[0]), float(ask[1])
                    if qty == 0:
                        self.orderbook['asks'] = [a for a in self.orderbook['asks'] if float(a[0]) != price]
                    else:
                        # Update or insert ask
                        updated = False
                        for i, a in enumerate(self.orderbook['asks']):
                            if float(a[0]) == price:
                                self.orderbook['asks'][i] = [ask[0], ask[1]]
                                updated = True
                                break
                        if not updated:
                            self.orderbook['asks'].append([ask[0], ask[1]])
                
                # Sort orderbook
                self.orderbook['bids'].sort(key=lambda x: float(x[0]), reverse=True)
                self.orderbook['asks'].sort(key=lambda x: float(x[0]))
                
        except Exception as e:
            logger.error(f"Error handling orderbook update: {e}")

    def _handle_snapshot(self, msg: Dict) -> None:
        """Handle orderbook snapshot from WebSocket."""
        try:
            if msg['e'] == 'depth' and msg['s'] == TRADING_PAIR:
                self.orderbook = {
                    'bids': [[price, qty] for price, qty in msg['bids']],
                    'asks': [[price, qty] for price, qty in msg['asks']]
                }
        except Exception as e:
            logger.error(f"Error handling orderbook snapshot: {e}")

    def _handle_trade_update(self, msg: Dict) -> None:
        """Handle trade updates from WebSocket."""
        try:
            if msg['e'] == 'executionReport' and msg['s'] == TRADING_PAIR:
                if msg['x'] == 'TRADE' and msg['S'] == 'BUY':
                    # Add trade to session trades
                    self._session_trades.append({
                        'time': msg['T'],
                        'qty': msg['q'],
                        'price': msg['p']
                    })
                    
                    # Update session stats
                    quantity = float(msg['q'])
                    price = float(msg['p'])
                    self._session_acquired_quantity += quantity
                    self._session_total_cost += quantity * price
                    
                    # Log progress
                    self._log_progress()
                    
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
                    self._total_cost += cost
                    self._total_quantity += quantity
                    
                    # Calculate weighted average price using filled quantity
                    if self._total_quantity > 0:
                        self._weighted_avg_price = self._total_cost / self._total_quantity
                
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
            
    def stop(self) -> None:
        """Stop monitoring and clean up."""
        if self._shutdown_in_progress:
            return
            
        self._shutdown_in_progress = True
        logger.info("Stopping trading monitor...")
        
        try:
            # Recalculate session stats from trades to ensure accuracy
            if self._session_trades:
                self._session_total_cost = sum(trade['cost'] for trade in self._session_trades)
                total_qty = sum(trade['qty'] for trade in self._session_trades)
                self._session_average_price = self._session_total_cost / total_qty if total_qty > 0 else 0

            # Show final summary if target was reached
            logger.info(f"{Colors.GREEN}=== SESSION SUMMARY ==={Colors.ENDC}")
            logger.info(f"{Colors.GREEN}Successfully accumulated {self._session_acquired_quantity:.8f} {BASE}{Colors.ENDC}")
            logger.info(f"{Colors.GREEN}Average Entry Price: {self._session_average_price:.8f} {QUOTE}{Colors.ENDC}")
            logger.info(f"{Colors.GREEN}Total Cost: {self._session_total_cost:.8f} {QUOTE}{Colors.ENDC}")
            
            # Cancel all open orders first
            try:
                open_orders = self.api.get_open_orders(TRADING_PAIR)
                for order in open_orders:
                    try:
                        self.api.cancel_order(TRADING_PAIR, order['orderId'])
                        logger.info(f"{Colors.YELLOW}Cancelled order {order['orderId']}{Colors.ENDC}")
                    except Exception as e:
                        logger.error(f"{Colors.RED}Error cancelling order {order['orderId']}: {e}{Colors.ENDC}")
            except Exception as e:
                logger.error(f"{Colors.RED}Error getting/cancelling open orders: {e}{Colors.ENDC}")
            
            # Stop all strategies first
            for name, strategy in self.strategies.items():
                try:
                    logger.info(f"Stopping {name} strategy...")
                    strategy.stop()
                except Exception as e:
                    logger.error(f"Error stopping {name} strategy: {e}")
            
            # Wait for strategy threads to finish
            for name, thread in self.strategy_threads.items():
                try:
                    if thread.is_alive():
                        logger.info(f"Waiting for {name} strategy thread to finish...")
                        thread.join(timeout=5)  # Wait up to 5 seconds
                        if thread.is_alive():
                            logger.warning(f"{name} strategy thread did not finish gracefully")
                except Exception as e:
                    logger.error(f"Error waiting for {name} strategy thread: {e}")
            
            # Stop WebSocket connections if they were initialized
            if self.ws_manager is not None:
                try:
                    # Close the user data stream if we have one
                    if self.user_stream is not None:
                        try:
                            self.ws_manager.stop_socket(self.user_stream)
                            logger.info("User data stream closed")
                        except Exception as e:
                            logger.error(f"Error stopping user data stream: {e}")
                    
                    # Stop the WebSocket manager
                    self.ws_manager.stop()
                    logger.info("WebSocket connections closed")
                except Exception as e:
                    logger.error(f"Error stopping WebSocket manager: {e}")
            
            # Clear all data structures
            self.strategies.clear()
            self.strategy_threads.clear()
            self.orderbook = {'bids': [], 'asks': []}
            self._session_trades.clear()
            
            # Log final statistics
            self._log_trade_summary()
            
            logger.info("Trading monitor stopped successfully")
            
        except Exception as e:
            logger.error(f"Error during shutdown: {e}")
        finally:
            self.running = False
            self._shutdown_in_progress = False

    def _log_progress(self) -> None:
        """Log current progress towards target."""
        try:
            # Get current balance
            current_balance = self.api.get_account_balance(BASE)
            if isinstance(current_balance, dict):
                current_quantity = float(current_balance.get('free', 0))
                locked_quantity = float(current_balance.get('locked', 0))
            else:
                current_quantity = float(current_balance)
                locked_quantity = 0.0
                
            # Calculate session-specific quantities
            session_acquired = current_quantity - self._session_start_quantity
            total_quantity = current_quantity + locked_quantity
            remaining = max(0, TARGET_QUANTITY - session_acquired)
            
            # Calculate session-specific costs and averages
            if self._session_acquired_quantity > 0:
                avg_price = self._session_average_price
                total_cost = self._session_total_cost
            else:
                total_cost = 0.0
                avg_price = 0.0
                
            # Log progress
            logger.info(f"{Colors.BOLD_WHITE}=== Current Status ==={Colors.ENDC}")
            logger.info(f"{Colors.BOLD_MAGENTA}Session Start Balance: {self._session_start_quantity:.8f} {BASE}{Colors.ENDC}")
            logger.info(f"{Colors.BOLD_MAGENTA}Current Balance: {current_quantity:.8f} {BASE}{Colors.ENDC}")
            logger.info(f"{Colors.BOLD_GREEN}Session Acquired: {session_acquired:.8f} {BASE}{Colors.ENDC}")
            logger.info(f"{Colors.BOLD_MAGENTA}Locked in Orders: {locked_quantity:.8f} {BASE}{Colors.ENDC}")
            logger.info(f"{Colors.BOLD_MAGENTA}Total (Balance + Locked): {total_quantity:.8f} {BASE}{Colors.ENDC}")
            logger.info(f"{Colors.BOLD_YELLOW}Target: {TARGET_QUANTITY:.8f} {BASE}{Colors.ENDC}")
            logger.info(f"{Colors.BOLD_YELLOW}Remaining: {remaining:.8f} {BASE}{Colors.ENDC}")
            logger.info(f"{Colors.BOLD_GREEN}Session Average Entry: {avg_price:.8f} {QUOTE}{Colors.ENDC}")
            logger.info(f"{Colors.BOLD_MAGENTA}Session Total Cost: {total_cost:.8f} {QUOTE}{Colors.ENDC}")
            logger.info(f"{Colors.BOLD_MAGENTA}Session Trades Count: {len(self._session_trades)}{Colors.ENDC}")
            
            # Get current price for remaining cost calculation
            orderbook = self.api.get_orderbook(TRADING_PAIR)
            if orderbook and orderbook['asks']:
                current_price = float(orderbook['asks'][0][0])
                if remaining != 0:
                    remaining_cost = (QUOTE_PRICE * TARGET_QUANTITY - avg_price) / remaining
                    logger.info(f"{Colors.BOLD_RED}Remaining Cost: {remaining_cost:.8f} {QUOTE}{Colors.ENDC}")
            
            # Log open orders
            open_orders = self.api.get_open_orders(TRADING_PAIR)
            if open_orders:
                logger.info(f"{Colors.PINK}Open Orders:{Colors.ENDC}")
                for order in open_orders:
                    logger.info(f"  {order['side']} {order['origQty']} {BASE} @ {order['price']} {QUOTE}")
                    
        except Exception as e:
            logger.error(f"{Colors.RED}Error logging progress: {e}{Colors.ENDC}")

    def _log_trade_summary(self) -> None:
        """Log a summary of all trades in this session."""
        try:
            return
            # if not self._session_trades:
            #     logger.info("\n=== Trade Summary ===")
            #     logger.info("No trades executed in this session")
            #     return
                
            # total_trades = len(self._session_trades)
            # total_quantity = sum(trade['qty'] for trade in self._session_trades)
            # total_cost = sum(trade['cost'] for trade in self._session_trades)
            # avg_price = total_cost / total_quantity if total_quantity > 0 else 0
            
            # logger.info("\n=== Trade Summary ===")
            # logger.info(f"Total Trades: {total_trades}")
            # logger.info(f"Total Quantity: {total_quantity:.8f} {BASE}")
            # logger.info(f"Total Cost: {total_cost:.8f} {QUOTE}")
            # logger.info(f"Weighted Average Entry: {avg_price:.8f} {QUOTE}")
            
            # logger.info("\nTrade Breakdown:")
            # for trade in self._session_trades:
            #     trade_time = datetime.fromtimestamp(trade['time']/1000)
            #     quantity = trade['qty']
            #     price = trade['price']
            #     cost = trade['cost']
            #     logger.info(f"  {trade_time} - Quantity: {quantity:.8f} {BASE}, Price: {price:.8f} {QUOTE}, Cost: {cost:.8f} {QUOTE}")
            
            # logger.info("\nFinal Statistics:")
            # logger.info(f"  Average Trade Size: {total_quantity/total_trades:.8f} {BASE}")
            # logger.info(f"  Total Value: {total_cost:.8f} {QUOTE}")
            # logger.info(f"  Average Entry Price: {avg_price:.8f} {QUOTE}")
            
        except Exception as e:
            return

    def get_remaining_quantity(self) -> float:
        """Get remaining quantity to acquire."""
        try:
            # Get current balance
            current_balance = self.api.get_account_balance(self.base)
            if isinstance(current_balance, dict):
                current_quantity = float(current_balance.get('free', 0))
                locked_quantity = float(current_balance.get('locked', 0))
            else:
                current_quantity = float(current_balance)
                locked_quantity = 0.0
                
            # Calculate session acquired amount
            session_acquired = current_quantity - self._session_start_quantity
            
            # Calculate remaining amount
            remaining = max(0, self.target_quantity - session_acquired)
            return remaining
            
        except Exception as e:
            logger.error(f"Error getting remaining quantity: {e}")
            return 0.0

    def _handle_user_update(self, msg: Dict) -> None:
        """Handle user data stream updates."""
        try:
            if msg['e'] == 'executionReport':
                # Handle order execution updates
                if msg['s'] == TRADING_PAIR:
                    if msg['x'] == 'TRADE' and msg['S'] == 'BUY' and msg['X'] == 'FILLED':
                        # Order was filled
                        quantity = float(msg['l'])  # Use 'l' (last executed quantity) instead of 'q'
                        price = float(msg['L'])     # Use 'L' (last executed price) instead of 'p'
                        cost = quantity * price
                        
                        # Add to session trades for tracking
                        self._session_trades.append({
                            'time': msg['T'],
                            'qty': quantity,
                            'price': price,
                            'cost': cost
                        })
                        
                        # Update session tracking
                        self._session_acquired_quantity += quantity
                        self._session_total_cost += cost
                        if self._session_acquired_quantity > 0:
                            self._session_average_price = self._session_total_cost / self._session_acquired_quantity
                        
                        # Log the fill with color
                        logger.info(f"{Colors.GREEN}Order filled: {quantity} {BASE} @ {price} {QUOTE} (Cost: {cost:.8f} {QUOTE}){Colors.ENDC}")
                        
                        # Update progress
                        self._log_progress()
                        
            elif msg['e'] == 'outboundAccountPosition':
                # Handle balance updates
                for balance in msg['B']:
                    if balance['a'] == BASE:
                        current_balance = float(balance['f'])
                        logger.info(f"{Colors.BLUE}Balance update: {current_balance} {BASE}{Colors.ENDC}")
                        
        except Exception as e:
            logger.error(f"{Colors.RED}Error handling user update: {e}{Colors.ENDC}")

    def _strategy_config_watcher(self):
        """Background thread to reload config_strategies.py every 10 seconds and start/stop strategies accordingly."""
        while self.running:
            try:
                spec = importlib.util.spec_from_file_location("config_strategies", "config_strategies.py")
                if spec is not None and spec.loader is not None:
                    config_strategies = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(config_strategies)
                    for name, strategy_class in [
                        ("shadow_bid", ShadowBidStrategy),
                        ("cooldown_taker", CooldownTakerStrategy),
                        ("big_fish", BigFishStrategy)
                    ]:
                        enabled = getattr(config_strategies, name.upper(), False)
                        is_running = name in self.strategies
                        logger.info(f"[Config] {name}: enabled={enabled}, is_running={is_running}")
                        if enabled and not is_running:
                            logger.info(f"[Config] Enabling {name} strategy (creating and starting thread)...")
                            try:
                                self.strategies[name] = strategy_class(self.api, self)
                                self._start_strategy(name)
                                logger.info(f"[Config] {name} strategy started.")
                            except Exception as e:
                                logger.error(f"[Config] Error starting {name} strategy: {e}")
                        elif not enabled and is_running:
                            logger.info(f"[Config] Disabling {name} strategy (stopping and deleting)...")
                            try:
                                self._stop_strategy(name)
                                del self.strategies[name]
                                logger.info(f"[Config] {name} strategy stopped and deleted.")
                            except Exception as e:
                                logger.error(f"[Config] Error stopping {name} strategy: {e}")
            except Exception as e:
                logger.error(f"Error reloading config_strategies.py: {e}")
            time.sleep(10)

def main():
    """Main entry point."""
    monitor = None
    try:
        # Set up signal handlers
        signal.signal(signal.SIGINT, lambda s, f: sys.exit(0))
        signal.signal(signal.SIGTERM, lambda s, f: sys.exit(0))
        
        # Create and start monitor
        monitor = TradingMonitor()
        monitor.start()
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt, shutting down...")
    except Exception as e:
        logger.error(f"Error in main: {e}")
        sys.exit(1)
    finally:
        if monitor:
            monitor.stop()
        logger.info("Program terminated.")
        
if __name__ == "__main__":
    main()