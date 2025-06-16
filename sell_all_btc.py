import logging
import time
from utils.binance_api import BinanceAPI
from config import BINANCE_API_KEY, BINANCE_API_SECRET, USE_TESTNET, TRADING_PAIR

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def sell_all_btc():
    """Sell all BTC holdings into USDT."""
    try:
        # Initialize API client
        api = BinanceAPI(
            api_key=BINANCE_API_KEY,
            api_secret=BINANCE_API_SECRET,
            use_testnet=USE_TESTNET
        )
        
        # Get BTC balance
        btc_balance = api.get_account_balance('BTC')
        if isinstance(btc_balance, dict):
            free_btc = float(btc_balance.get('free', 0))
            locked_btc = float(btc_balance.get('locked', 0))
        else:
            free_btc = float(btc_balance)
            locked_btc = 0.0
        total_btc = free_btc + locked_btc
        
        if total_btc <= 0:
            logger.info("No BTC to sell")
            return
            
        logger.info(f"Found {total_btc:.8f} BTC to sell")
        
        # Get current price
        orderbook = api.get_orderbook(TRADING_PAIR)
        if not orderbook or not orderbook['bids']:
            logger.error("Could not get current price")
            return
            
        current_price = float(orderbook['bids'][0][0])
        logger.info(f"Current BTC price: {current_price:.2f} USDT")
        
        # Place market sell order
        if free_btc > 0:
            logger.info(f"Placing market sell order for {free_btc:.8f} BTC")
            order = api.place_market_order(
                pair=TRADING_PAIR,
                side='SELL',
                quantity=free_btc
            )
            logger.info(f"Market sell order placed: {order}")
            
        # Wait for order to fill
        time.sleep(5)
        
        # Check final balance
        final_balance = api.get_account_balance('BTC')
        if final_balance:
            remaining_btc = float(final_balance['free']) + float(final_balance['locked'])
            logger.info(f"Remaining BTC: {remaining_btc:.8f}")
            
        logger.info("Sell operation completed")
        
    except Exception as e:
        logger.error(f"Error selling BTC: {e}")
        raise

if __name__ == "__main__":
    sell_all_btc() 