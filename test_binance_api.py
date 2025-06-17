from utils.binance_api import BinanceAPI
from config import BINANCE_API_KEY, BINANCE_API_SECRET, USE_TESTNET, TRADING_PAIR
import time

def test_binance_api():
    # Initialize API client with credentials from config
    api = BinanceAPI(
        api_key=BINANCE_API_KEY,
        api_secret=BINANCE_API_SECRET,
        use_testnet=USE_TESTNET
    )

    # Test pair from config
    test_pair = TRADING_PAIR

    try:
        # 1. Test getting best bid/ask
        print("\n1. Testing get_best_bid_ask...")
        best_bid, best_ask = api.get_best_bid_ask(test_pair)
        print(f"Best bid: {best_bid}")
        print(f"Best ask: {best_ask}")

        # 2. Test getting orderbook
        print("\n2. Testing get_orderbook...")
        orderbook = api.get_orderbook(test_pair, limit=5)
        print("Top 5 bids:")
        for bid in orderbook['bids'][:5]:
            print(f"Price: {bid[0]}, Quantity: {bid[1]}")
        print("\nTop 5 asks:")
        for ask in orderbook['asks'][:5]:
            print(f"Price: {ask[0]}, Quantity: {ask[1]}")

        # 3. Test getting account balance
        print("\n3. Testing get_account_balance...")
        usdt_balance = api.get_account_balance("USDT")
        btc_balance = api.get_account_balance("BTC")
        print(f"USDT Balance: {usdt_balance}")
        print(f"BTC Balance: {btc_balance}")

        # 4. Test placing a limit order (small amount)
        print("\n4. Testing place_limit_order...")
        # Place a limit buy order slightly below current price
        test_price = float(best_bid) * 1  # 1% below best bid
        test_quantity = 6.0  # Small amount for testing
        order = api.place_limit_order(
            pair=test_pair,
            price=test_price,
            quantity=test_quantity,
            side='BUY'
        )
        print(f"Placed order: {order}")

        # 5. Test getting order status
        print("\n5. Testing get_order_status...")
        order_status = api.get_order_status(test_pair, order['orderId'])
        print(f"Order status: {order_status}")

        # 6. Test canceling the order
        print("\n6. Testing cancel_order...")
        cancel_result = api.cancel_order(test_pair, order['orderId'])
        print(f"Cancel result: {cancel_result}")

    except Exception as e:
        print(f"Error during testing: {e}")

if __name__ == "__main__":
    test_binance_api() 