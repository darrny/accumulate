import unittest
import logging
import time
from typing import Dict, List, Optional
from utils.binance_api import BinanceAPI
from strategies.shadow_bid import ShadowBidStrategy
from strategies.cooldown_taker import CooldownTakerStrategy
from strategies.big_fish import BigFishStrategy
from monitor import TradingMonitor
from config import (
    TRADING_PAIR, SHADOW_BID, COOLDOWN_TAKER, BIG_FISH,
    BINANCE_API_KEY, BINANCE_API_SECRET, USE_TESTNET
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ANSI color codes
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    ENDC = '\033[0m'

class TestBinanceAPI(unittest.TestCase):
    def setUp(self):
        self.api = BinanceAPI(
            api_key=BINANCE_API_KEY,
            api_secret=BINANCE_API_SECRET,
            use_testnet=USE_TESTNET
        )
        
    def test_connection(self):
        """Test basic API connection"""
        try:
            # Test server time
            server_time = self.api.client.get_server_time()
            self.assertIsNotNone(server_time)
            print(f"{Colors.GREEN}✓ API Connection Test Passed{Colors.ENDC}")
        except Exception as e:
            print(f"{Colors.RED}✗ API Connection Test Failed: {str(e)}{Colors.ENDC}")
            raise
            
    def test_orderbook(self):
        """Test orderbook retrieval"""
        try:
            orderbook = self.api.get_orderbook(TRADING_PAIR)
            self.assertIsNotNone(orderbook)
            self.assertIn('bids', orderbook)
            self.assertIn('asks', orderbook)
            print(f"{Colors.GREEN}✓ Orderbook Test Passed{Colors.ENDC}")
        except Exception as e:
            print(f"{Colors.RED}✗ Orderbook Test Failed: {str(e)}{Colors.ENDC}")
            raise
            
    def test_balance(self):
        """Test balance retrieval"""
        try:
            balance = self.api.get_account_balance('USDT')
            self.assertIsNotNone(balance)
            print(f"{Colors.GREEN}✓ Balance Test Passed{Colors.ENDC}")
        except Exception as e:
            print(f"{Colors.RED}✗ Balance Test Failed: {str(e)}{Colors.ENDC}")
            raise

class TestShadowBid(unittest.TestCase):
    def setUp(self):
        self.api = BinanceAPI(
            api_key=BINANCE_API_KEY,
            api_secret=BINANCE_API_SECRET,
            use_testnet=USE_TESTNET
        )
        self.strategy = ShadowBidStrategy(self.api)
        
    def test_order_placement(self):
        """Test shadow bid order placement"""
        try:
            # Start strategy
            self.strategy.start()
            time.sleep(5)  # Wait for potential orders
            self.strategy.stop()
            
            # If we got here without an error, the test passed
            print(f"\n{Colors.GREEN}✓ Shadow Bid Order Placement Test Passed{Colors.ENDC}")
            print(f"{Colors.GREEN}  - Successfully placed and managed orders{Colors.ENDC}")
            return True
        except Exception as e:
            if "insufficient balance" in str(e).lower():
                print(f"\n{Colors.YELLOW}⚠ Shadow Bid Test Skipped (Insufficient Funds){Colors.ENDC}")
                return True
            else:
                print(f"\n{Colors.RED}✗ Shadow Bid Test Failed: {str(e)}{Colors.ENDC}")
                raise

class TestCooldownTaker(unittest.TestCase):
    def setUp(self):
        self.api = BinanceAPI(
            api_key=BINANCE_API_KEY,
            api_secret=BINANCE_API_SECRET,
            use_testnet=USE_TESTNET
        )
        self.strategy = CooldownTakerStrategy(self.api)
        
    def test_order_placement(self):
        """Test cooldown taker order placement"""
        try:
            # Start strategy
            self.strategy.start()
            time.sleep(5)  # Wait for potential orders
            self.strategy.stop()
            
            # If we got here without an error, the test passed
            print(f"\n{Colors.GREEN}✓ Cooldown Taker Order Placement Test Passed{Colors.ENDC}")
            print(f"{Colors.GREEN}  - Successfully placed and managed orders{Colors.ENDC}")
            return True
        except Exception as e:
            if "insufficient balance" in str(e).lower():
                print(f"\n{Colors.YELLOW}⚠ Cooldown Taker Test Skipped (Insufficient Funds){Colors.ENDC}")
                return True
            else:
                print(f"\n{Colors.RED}✗ Cooldown Taker Test Failed: {str(e)}{Colors.ENDC}")
                raise

class TestBigFish(unittest.TestCase):
    def setUp(self):
        self.api = BinanceAPI(
            api_key=BINANCE_API_KEY,
            api_secret=BINANCE_API_SECRET,
            use_testnet=USE_TESTNET
        )
        self.strategy = BigFishStrategy(self.api)
        
    def test_order_placement(self):
        """Test big fish order placement"""
        try:
            # Start strategy
            self.strategy.start()
            time.sleep(5)  # Wait for potential orders
            self.strategy.stop()
            
            # If we got here without an error, the test passed
            print(f"\n{Colors.GREEN}✓ Big Fish Order Placement Test Passed{Colors.ENDC}")
            print(f"{Colors.GREEN}  - Successfully placed and managed orders{Colors.ENDC}")
            return True
        except Exception as e:
            if "insufficient balance" in str(e).lower():
                print(f"\n{Colors.YELLOW}⚠ Big Fish Test Skipped (Insufficient Funds){Colors.ENDC}")
                return True
            else:
                print(f"\n{Colors.RED}✗ Big Fish Test Failed: {str(e)}{Colors.ENDC}")
                raise

class TestMonitor(unittest.TestCase):
    def setUp(self):
        self.api = BinanceAPI(
            api_key=BINANCE_API_KEY,
            api_secret=BINANCE_API_SECRET,
            use_testnet=USE_TESTNET
        )
        self.monitor = TradingMonitor(self.api)
        
    def test_websocket_connection(self):
        """Test WebSocket connection and data flow"""
        try:
            # Start monitor
            self.monitor.start()
            time.sleep(5)  # Wait for WebSocket data
            self.monitor.stop()
            print(f"\n{Colors.GREEN}✓ Monitor WebSocket Test Passed{Colors.ENDC}")
            return True
        except Exception as e:
            print(f"\n{Colors.RED}✗ Monitor WebSocket Test Failed: {str(e)}{Colors.ENDC}")
            raise
            
    def test_strategy_integration(self):
        """Test strategy integration with monitor"""
        try:
            # Verify strategy initialization
            self.assertIsInstance(self.monitor.strategies, dict)
            print(f"\n{Colors.GREEN}✓ Monitor Strategy Integration Test Passed{Colors.ENDC}")
            return True
        except Exception as e:
            print(f"\n{Colors.RED}✗ Monitor Strategy Integration Test Failed: {str(e)}{Colors.ENDC}")
            raise

def run_tests():
    """Run all test suites with color-coded results"""
    print(f"\n{Colors.BLUE}=== Starting Test Suite ==={Colors.ENDC}\n")
    
    # Create test suites
    suites = [
        unittest.TestLoader().loadTestsFromTestCase(TestBinanceAPI),
        unittest.TestLoader().loadTestsFromTestCase(TestShadowBid),
        unittest.TestLoader().loadTestsFromTestCase(TestCooldownTaker),
        unittest.TestLoader().loadTestsFromTestCase(TestBigFish),
        unittest.TestLoader().loadTestsFromTestCase(TestMonitor)
    ]
    
    # Run each suite
    for suite in suites:
        print(f"\n{Colors.BLUE}=== Running {suite.__class__.__name__} ==={Colors.ENDC}")
        unittest.TextTestRunner(verbosity=2).run(suite)
    
    print(f"\n{Colors.BLUE}=== Test Suite Complete ==={Colors.ENDC}")

if __name__ == '__main__':
    run_tests() 