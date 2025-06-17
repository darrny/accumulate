from binance.client import Client
from binance.exceptions import BinanceAPIException
import logging
from typing import Tuple, Optional, Dict, Any, List, Union
import time

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('binance_api')

class BinanceAPI:
    def __init__(self, api_key: str, api_secret: str, use_testnet: bool = False):
        """
        Initialize Binance API client with credentials.
        
        Args:
            api_key: Binance API key
            api_secret: Binance API secret
            use_testnet: Whether to use testnet (default: False)
        """
        self.client = Client(api_key, api_secret, testnet=use_testnet)
        logger.info(f"Initialized Binance API client (testnet: {use_testnet})")
        self._validate_connection()
        
    def _validate_connection(self) -> None:
        """Validate API connection by making a test request."""
        try:
            self.client.ping()
            logger.info("Successfully connected to Binance API")
        except BinanceAPIException as e:
            logger.error(f"Failed to connect to Binance API: {e}")
            raise

    def get_best_bid_ask(self, pair: str) -> Tuple[float, float]:
        """
        Get the best bid and ask prices for a trading pair.
        
        Args:
            pair: Trading pair (e.g., 'UNIUSDT')
            
        Returns:
            Tuple of (best_bid, best_ask) prices
        """
        try:
            ticker = self.client.get_order_book(symbol=pair, limit=1)
            best_bid = float(ticker['bids'][0][0])
            best_ask = float(ticker['asks'][0][0])
            return best_bid, best_ask
        except BinanceAPIException as e:
            logger.error(f"Error getting best bid/ask for {pair}: {e}")
            raise

    def place_limit_order(self, pair: str, price: float, quantity: float, 
                         side: str = 'BUY', post_only: bool = False) -> Dict[str, Any]:
        """
        Place a limit order on Binance.
        
        Args:
            pair: Trading pair (e.g., 'UNIUSDT')
            price: Limit price
            quantity: Order quantity
            side: 'BUY' or 'SELL'
            post_only: Whether to make this a post-only order
            
        Returns:
            Order response from Binance
        """
        try:
            params = {
                'symbol': pair,
                'side': side,
                'type': 'LIMIT',
                'timeInForce': 'GTC',
                'quantity': quantity,
                'price': price
            }
            
            if post_only:
                params['newOrderRespType'] = 'RESULT'
                params['newClientOrderId'] = f'post_only_{int(time.time() * 1000)}'
            
            order = self.client.create_order(**params)
            return order
        except BinanceAPIException as e:
            logger.error(f"Error placing limit order for {pair}: {e}")
            raise

    def place_market_order(self, pair: str, quantity: float, side: str = 'BUY') -> Dict[str, Any]:
        """
        Place a market order on Binance.
        Args:
            pair: Trading pair (e.g., 'UNIUSDT')
            quantity: Order quantity
            side: 'BUY' or 'SELL'
        Returns:
            Order response from Binance
        """
        try:
            params = {
                'symbol': pair,
                'side': side,
                'type': 'MARKET',
                'quantity': quantity
            }
            order = self.client.create_order(**params)
            logger.info(f"Placed {side} market order for {quantity} {pair}")
            return order
        except BinanceAPIException as e:
            logger.error(f"Error placing market order for {pair}: {e}")
            raise

    def cancel_order(self, pair: str, order_id: int) -> Dict[str, Any]:
        """
        Cancel an existing order.
        
        Args:
            pair: Trading pair (e.g., 'UNIUSDT')
            order_id: ID of the order to cancel
            
        Returns:
            Cancellation response from Binance
        """
        try:
            result = self.client.cancel_order(
                symbol=pair,
                orderId=order_id
            )
            logger.info(f"Cancelled order {order_id} for {pair}")
            return result
        except BinanceAPIException as e:
            logger.error(f"Error cancelling order {order_id} for {pair}: {e}")
            raise

    def get_order_status(self, pair: str, order_id: int) -> Dict[str, Any]:
        """
        Get the status of an existing order.
        
        Args:
            pair: Trading pair (e.g., 'UNIUSDT')
            order_id: ID of the order to check
            
        Returns:
            Order status from Binance
        """
        try:
            order = self.client.get_order(
                symbol=pair,
                orderId=order_id
            )
            return order
        except BinanceAPIException as e:
            logger.error(f"Error getting status for order {order_id} on {pair}: {e}")
            raise

    def get_account_balance(self, asset: str) -> Union[Dict, float]:
        """
        Get the balance of a specific asset.
        
        Args:
            asset: Asset symbol (e.g., 'USDT')
            
        Returns:
            Available balance of the asset
        """
        try:
            account = self.client.get_account()
            for balance in account['balances']:
                if balance['asset'] == asset:
                    return balance
            return 0.0
        except BinanceAPIException as e:
            logger.error(f"Error getting balance for {asset}: {e}")
            return 0.0

    def get_orderbook(self, pair: str, limit: int = 100) -> Dict:
        """
        Get the orderbook for a trading pair.
        
        Args:
            pair: Trading pair (e.g., 'UNIUSDT')
            limit: Number of orders to retrieve (max 5000)
            
        Returns:
            Orderbook data from Binance with preserved string precision
        """
        try:
            orderbook = self.client.get_order_book(symbol=pair, limit=limit)
            # Keep the values as strings to preserve precision
            return {
                'bids': [[price, qty] for price, qty in orderbook['bids']],
                'asks': [[price, qty] for price, qty in orderbook['asks']]
            }
        except BinanceAPIException as e:
            logger.error(f"Error getting orderbook for {pair}: {e}")
            return {'bids': [], 'asks': []}

    def get_exchange_info(self) -> Dict:
        """
        Get exchange information including trading rules and filters.
        
        Returns:
            Dict containing exchange information
        """
        try:
            response = self.client.get_exchange_info()
            return response
        except Exception as e:
            logger.error(f"Error getting exchange info: {e}")
            raise

    def get_recent_trades(self, symbol: str, limit: int = 100) -> List[Dict]:
        """Get recent trades for a symbol."""
        try:
            return self.client.get_recent_trades(symbol=symbol, limit=limit)
        except BinanceAPIException as e:
            logger.error(f"Error getting recent trades: {e}")
            return []

    def place_order(self, symbol: str, side: str, order_type: str, 
                   quantity: float, price: Optional[float] = None,
                   time_in_force: str = 'GTC') -> Dict:
        """Place an order."""
        try:
            params = {
                'symbol': symbol,
                'side': side,
                'type': order_type,
                'quantity': quantity,
                'timeInForce': time_in_force
            }
            
            if price and order_type == 'LIMIT':
                params['price'] = price
                
            return self.client.create_order(**params)
        except BinanceAPIException as e:
            logger.error(f"Error placing order: {e}")
            return {}

    def get_open_orders(self, symbol: Optional[str] = None) -> List[Dict]:
        """Get open orders."""
        try:
            if symbol:
                return self.client.get_open_orders(symbol=symbol)
            return self.client.get_open_orders()
        except BinanceAPIException as e:
            logger.error(f"Error getting open orders: {e}")
            return []
