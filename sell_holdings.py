import logging
from binance.client import Client
from config import USE_TESTNET, BINANCE_API_KEY, BINANCE_API_SECRET, TRADING_PAIR
from utils.binance_api import BinanceAPI

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def sell_holdings(quantity: float):
    """
    Sell a specified quantity of the trading pair
    
    Args:
        quantity (float): Amount to sell
    """
    try:
        # Initialize API with credentials
        api = BinanceAPI(api_key=BINANCE_API_KEY, api_secret=BINANCE_API_SECRET)
        
        # Get current price
        ticker = api.client.get_symbol_ticker(symbol=TRADING_PAIR)
        current_price = float(ticker['price'])
        
        # Place market sell order
        order = api.client.create_order(
            symbol=TRADING_PAIR,
            side='SELL',
            type='MARKET',
            quantity=quantity
        )
        
        logger.info(f"Successfully placed market sell order for {quantity} {TRADING_PAIR}")
        logger.info(f"Order details: {order}")
        
        # Calculate approximate value
        value = quantity * current_price
        logger.info(f"Approximate value: {value} USDT")
        
    except Exception as e:
        logger.error(f"Error selling holdings: {str(e)}")
        raise

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Sell holdings of the trading pair')
    parser.add_argument('quantity', type=float, help='Amount to sell')
    
    args = parser.parse_args()
    sell_holdings(args.quantity) 