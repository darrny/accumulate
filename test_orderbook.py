from utils.binance_api import BinanceAPI
from config import BINANCE_API_KEY, BINANCE_API_SECRET, USE_TESTNET, TRADING_PAIR
import json

def main():
    # Initialize API
    api = BinanceAPI(BINANCE_API_KEY, BINANCE_API_SECRET, USE_TESTNET)
    
    # Get raw orderbook
    orderbook = api.client.get_order_book(symbol=TRADING_PAIR, limit=5)
    
    print("\nRaw orderbook data:")
    print(json.dumps(orderbook, indent=2))
    
    # Get exchange info
    exchange_info = api.get_exchange_info()
    symbol_info = next((s for s in exchange_info['symbols'] if s['symbol'] == TRADING_PAIR), None)
    
    print("\nSymbol info:")
    print(json.dumps(symbol_info, indent=2))

if __name__ == "__main__":
    main() 