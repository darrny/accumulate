import logging
import time
import sys
from typing import Dict, Optional
from binance.client import Client
from binance import ThreadedWebsocketManager
from utils.binance_api import BinanceAPI
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
        logger.info(f"Current quantity: {current_quantity:.8f} / Target: {self.target_quantity:.8f}")
        return current_quantity >= self.target_quantity
            
    def _handle_orderbook_update(self, msg: Dict) -> None:
        """Handle orderbook update from WebSocket."""
        try:
            # Update orderbook
            self.orderbook['bids'] = [(float(price), float(qty)) for price, qty in msg['b']]
            self.orderbook['asks'] = [(float(price), float(qty)) for price, qty in msg['a']]
            
            # Log top of book
            if self.orderbook['bids'] and self.orderbook['asks']:
                best_bid = self.orderbook['bids'][0]
                best_ask = self.orderbook['asks'][0]
                spread = best_ask[0] - best_bid[0]
                spread_pct = (spread / best_bid[0]) * 100
                
                logger.info(f"\nOrderbook Update:")
                logger.info(f"Best Bid: {best_bid[0]:.2f} ({best_bid[1]:.4f})")
                logger.info(f"Best Ask: {best_ask[0]:.2f} ({best_ask[1]:.4f})")
                logger.info(f"Spread: {spread:.2f} ({spread_pct:.3f}%)")
                
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
            
            # Only log trades above a certain quantity threshold
            if self.last_trade['quantity'] >= 0.1:  # Only log trades >= 0.1 BTC
                side = "SELL" if self.last_trade['is_buyer_maker'] else "BUY"
                logger.info(f"\nTrade Update (Large Trade):")
                logger.info(f"Price: {self.last_trade['price']:.2f}")
                logger.info(f"Quantity: {self.last_trade['quantity']:.4f}")
                logger.info(f"Side: {side}")
            
            # Check if we've reached target
            if self._check_target_reached():
                logger.info("Target quantity reached! Stopping all strategies...")
                self.stop()
                sys.exit(0)
                
        except Exception as e:
            logger.error(f"Error handling trade update: {e}")
            
    def _handle_balance_update(self, msg: Dict) -> None:
        """Handle balance update from WebSocket."""
        try:
            # Log balance update
            logger.info(f"\nBalance Update:")
            logger.info(f"Asset: {msg['a']}")
            logger.info(f"Free: {float(msg['f']):.8f}")
            logger.info(f"Locked: {float(msg['l']):.8f}")
            
            # Check if we've reached target
            if self._check_target_reached():
                logger.info("Target quantity reached! Stopping all strategies...")
                self.stop()
                sys.exit(0)
                
        except Exception as e:
            logger.error(f"Error handling balance update: {e}")
            
    def start(self) -> None:
        """Start monitoring with WebSocket."""
        logger.info("Starting trading monitor...")
        self.running = True
        
        try:
            # Initialize WebSocket manager with API client
            self.twm = ThreadedWebsocketManager(api_key=BINANCE_API_KEY, api_secret=BINANCE_API_SECRET)
            # start is required to initialise its internal loop
            self.twm.start()
            
            # Start WebSocket streams
            self.conn_key = self.twm.start_depth_socket(
                symbol=TRADING_PAIR.lower(),
                callback=self._handle_orderbook_update
            )
            self.twm.start_trade_socket(
                symbol=TRADING_PAIR.lower(),
                callback=self._handle_trade_update
            )
            
            # Try to start user data stream if API keys are valid
            try:
                user_stream = self.twm.start_user_socket(
                    callback=self._handle_balance_update
                )
                logger.info("User data stream started successfully")
            except Exception as e:
                logger.warning(f"Could not start user data stream: {e}")
                logger.info("Continuing without user data stream...")
            
            # Start strategies
            for name, strategy in self.strategies.items():
                logger.info(f"Starting {name} strategy...")
                strategy.start()
                
            # Keep the main thread alive
            while self.running:
                time.sleep(1)
                
        except KeyboardInterrupt:
            logger.info("Stopping monitor...")
        except Exception as e:
            logger.error(f"Error in monitor: {e}")
        finally:
            self.stop()
            
    def stop(self) -> None:
        """Stop monitoring and clean up."""
        logger.info("Stopping monitor...")
        self.running = False
        
        # Stop strategies
        for name, strategy in self.strategies.items():
            logger.info(f"Stopping {name} strategy...")
            strategy.stop()
            
        # Stop WebSocket connections
        if hasattr(self, 'twm'):
            self.twm.stop()
            logger.info("WebSocket connections closed")

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
        logger.error(f"Error in main: {e}")
        raise

if __name__ == "__main__":
    main()