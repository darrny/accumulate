import logging
import json
from datetime import datetime
from config import USE_TESTNET, TRADING_PAIR, BINANCE_API_KEY, BINANCE_API_SECRET
from utils.binance_api import BinanceAPI

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def get_account_info():
    """Get and display comprehensive account information"""
    try:
        # Initialize API with credentials
        api = BinanceAPI(api_key=BINANCE_API_KEY, api_secret=BINANCE_API_SECRET)
        
        # Get account information
        account = api.client.get_account()
        
        # Get current prices for all assets
        prices = api.client.get_all_tickers()
        price_dict = {item['symbol']: float(item['price']) for item in prices}
        
        # Get open orders
        open_orders = api.client.get_open_orders(symbol=TRADING_PAIR)
        
        # Get recent trades
        recent_trades = api.client.get_my_trades(symbol=TRADING_PAIR, limit=5)
        
        # Print account information
        logger.info("\n=== Account Information ===")
        logger.info(f"Account Type: {'Testnet' if USE_TESTNET else 'Production'}")
        logger.info(f"Account Status: {account['accountType']}")
        logger.info(f"Can Trade: {account['canTrade']}")
        logger.info(f"Can Withdraw: {account['canWithdraw']}")
        logger.info(f"Can Deposit: {account['canDeposit']}")
        
        # Print balances with non-zero amounts
        logger.info("\n=== Balances ===")
        for balance in account['balances']:
            free = float(balance['free'])
            locked = float(balance['locked'])
            if free > 0 or locked > 0:
                asset = balance['asset']
                # Calculate USD value if possible
                usd_value = 0
                if asset == 'USDT':
                    usd_value = free + locked
                elif f"{asset}USDT" in price_dict:
                    usd_value = (free + locked) * price_dict[f"{asset}USDT"]
                
                logger.info(f"{asset}:")
                logger.info(f"  Free: {free}")
                logger.info(f"  Locked: {locked}")
                if usd_value > 0:
                    logger.info(f"  USD Value: ${usd_value:.2f}")
        
        # Print open orders
        logger.info("\n=== Open Orders ===")
        if open_orders:
            for order in open_orders:
                logger.info(f"Order ID: {order['orderId']}")
                logger.info(f"Symbol: {order['symbol']}")
                logger.info(f"Side: {order['side']}")
                logger.info(f"Type: {order['type']}")
                logger.info(f"Price: {order['price']}")
                logger.info(f"Quantity: {order['origQty']}")
                logger.info(f"Time: {datetime.fromtimestamp(order['time']/1000)}")
                logger.info("---")
        else:
            logger.info("No open orders")
        
        # Print recent trades
        logger.info("\n=== Recent Trades ===")
        if recent_trades:
            for trade in recent_trades:
                logger.info(f"Trade ID: {trade['id']}")
                logger.info(f"Symbol: {trade['symbol']}")
                logger.info(f"Side: {trade['side']}")
                logger.info(f"Price: {trade['price']}")
                logger.info(f"Quantity: {trade['qty']}")
                logger.info(f"Commission: {trade['commission']} {trade['commissionAsset']}")
                logger.info(f"Time: {datetime.fromtimestamp(trade['time']/1000)}")
                logger.info("---")
        else:
            logger.info("No recent trades")
            
    except Exception as e:
        logger.error(f"Error getting account information: {str(e)}")
        raise

if __name__ == "__main__":
    get_account_info() 