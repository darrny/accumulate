from utils.binance_api import BinanceAPI
from strategies.shadow_bid import ShadowBidStrategy
from config import BINANCE_API_KEY, BINANCE_API_SECRET, USE_TESTNET
import time
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

def test_shadow_bid():
    # Initialize API client
    api = BinanceAPI(
        api_key=BINANCE_API_KEY,
        api_secret=BINANCE_API_SECRET,
        use_testnet=USE_TESTNET
    )
    
    # Create and start shadow bid strategy
    strategy = ShadowBidStrategy(api)
    
    try:
        print("Starting shadow bid strategy...")
        strategy.start()
        
        # Let it run for 30 seconds
        time.sleep(30)
        
    except KeyboardInterrupt:
        print("\nStopping shadow bid strategy...")
    finally:
        strategy.stop()
        print("Strategy stopped")

if __name__ == "__main__":
    test_shadow_bid() 