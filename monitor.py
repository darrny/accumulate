import logging
import time
import sys
import json
import uuid
from typing import Dict, Optional
from binance.client import Client
from binance import ThreadedWebsocketManager
from binance import AsyncClient, BinanceSocketManager
from utils.binance_api import BinanceAPI
from utils.ed25519_auth import get_user_data_stream, close_user_data_stream
from config import TRADING_PAIR, SHADOW_BID, COOLDOWN_TAKER, BIG_FISH, TARGET_QUANTITY, BINANCE_API_KEY, BINANCE_API_SECRET, USE_TESTNET
from strategies.shadow_bid import ShadowBidStrategy
from strategies.cooldown_taker import CooldownTakerStrategy
from strategies.big_fish import BigFishStrategy

# ANSI color codes
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

# Strategy colors
STRATEGY_COLORS = {
    'shadow_bid': Colors.CYAN,
    'cooldown_taker': Colors.YELLOW,
    'big_fish': Colors.GREEN
}

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class TradingMonitor:
    def __init__(self, api: BinanceAPI):
        self.api = api
        self.strategies = {}
        self.orderbook = {'bids': [], 'asks': []}
        self.last_trade = None
        self.running = False
        self.target_quantity = TARGET_QUANTITY
        self.twm = None
        self.conn_key = None
        self.user_stream = None
        
        # Track acquisition metrics
        self.acquired_quantity = 0.0
        self.total_cost = 0.0
        self.average_price = 0.0
        
        # Initialize strategies if enabled
        if SHADOW_BID['enabled']:
            self.strategies['shadow_bid'] = ShadowBidStrategy(api)
        if COOLDOWN_TAKER['enabled']:
            self.strategies['cooldown_taker'] = CooldownTakerStrategy(api)
        if BIG_FISH['enabled']:
            self.strategies['big_fish'] = BigFishStrategy(api)
            
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
        logger.info(f"{Colors.BOLD}{Colors.BLUE}Progress: {current_quantity:.8f} / {self.target_quantity:.8f} BTC (Remaining: {remaining:.8f} BTC){Colors.ENDC}")
        return current_quantity >= self.target_quantity
            
    def _handle_orderbook_update(self, msg: Dict) -> None:
        """Handle orderbook update from WebSocket."""
        try:
            # Update orderbook
            self.orderbook['bids'] = [(float(price), float(qty)) for price, qty in msg['b']]
            self.orderbook['asks'] = [(float(price), float(qty)) for price, qty in msg['a']]
            
            # Only log orderbook state if cooldown_taker or big_fish strategies are active
            if (COOLDOWN_TAKER['enabled'] or BIG_FISH['enabled']) and self.orderbook['bids'] and self.orderbook['asks']:
                logger.info(f"\n{Colors.BOLD}=== Current Orderbook State ==={Colors.ENDC}")
                logger.info(f"{Colors.BOLD}Top 5 Bids:{Colors.ENDC}")
                for price, qty in self.orderbook['bids'][:5]:
                    logger.info(f"  {price:.2f} USDT - {qty:.8f} BTC")
                logger.info(f"\n{Colors.BOLD}Top 5 Asks:{Colors.ENDC}")
                for price, qty in self.orderbook['asks'][:5]:
                    logger.info(f"  {price:.2f} USDT - {qty:.8f} BTC")
                logger.info(f"{Colors.BOLD}============================={Colors.ENDC}")
                
        except Exception as e:
            logger.error(f"Error handling orderbook update: {e}")
            
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
                # Update acquisition metrics for filled orders
                if event['X'] == 'FILLED' and event['S'] == 'BUY':
                    quantity = float(event['q'])
                    price = float(event['p'])
                    cost = quantity * price
                    
                    # Update metrics
                    self.acquired_quantity += quantity
                    self.total_cost += cost
                    self.average_price = self.total_cost / self.acquired_quantity if self.acquired_quantity > 0 else 0
                    
                    # Log acquisition with color
                    logger.info(f"\n{Colors.BOLD}{Colors.GREEN}=== Acquisition Update ==={Colors.ENDC}")
                    logger.info(f"{Colors.GREEN}Filled: {quantity:.8f} BTC @ {price:.2f} USDT{Colors.ENDC}")
                    logger.info(f"{Colors.GREEN}Total Acquired: {self.acquired_quantity:.8f} / {self.target_quantity:.8f} BTC{Colors.ENDC}")
                    logger.info(f"{Colors.GREEN}Average Price: {self.average_price:.2f} USDT{Colors.ENDC}")
                    logger.info(f"{Colors.GREEN}Remaining Cost: {(self.target_quantity - self.acquired_quantity) * self.average_price:.2f} USDT{Colors.ENDC}")
                    logger.info(f"{Colors.GREEN}========================={Colors.ENDC}")
                
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
            logger.error(f"Error handling balance update: {e}")
            logger.error(f"Message: {msg}")
            
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
            
            # Start strategies
            for name, strategy in self.strategies.items():
                color = STRATEGY_COLORS.get(name, Colors.ENDC)
                logger.info(f"{color}Starting {name} strategy...{Colors.ENDC}")
                strategy.start()
                
            # Keep the main thread alive
            while self.running:
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
        
        # Stop strategies
        for name, strategy in self.strategies.items():
            color = STRATEGY_COLORS.get(name, Colors.ENDC)
            logger.info(f"{color}Stopping {name} strategy...{Colors.ENDC}")
            strategy.stop()
            
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