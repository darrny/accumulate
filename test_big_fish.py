import logging
from utils.binance_api import BinanceAPI
from strategies.big_fish import BigFishStrategy
from config import BINANCE_API_KEY, BINANCE_API_SECRET, USE_TESTNET
import time

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def test_big_fish():
    """
    Test the big fish strategy.
    """
    # Initialize API client
    api = BinanceAPI(
        api_key=BINANCE_API_KEY,
        api_secret=BINANCE_API_SECRET,
        use_testnet=USE_TESTNET
    )
    
    # Initialize strategy
    strategy = BigFishStrategy(api)
    
    try:
        # Start strategy
        logger.info("Starting big fish strategy...")
        strategy.start()
        
        # Run for 5 minutes
        time.sleep(300)
        
    except KeyboardInterrupt:
        logger.info("Test interrupted by user")
    finally:
        # Stop strategy
        strategy.stop()
        logger.info("Strategy stopped")

if __name__ == "__main__":
    test_big_fish() 