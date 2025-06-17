from utils.binance_api import BinanceAPI
from strategies.cooldown_taker import CooldownTakerStrategy
from config import BINANCE_API_KEY, BINANCE_API_SECRET, USE_TESTNET, TRADING_PAIR
import time
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

def print_orderbook_state(api: BinanceAPI, depth: int = 3):
    """Print the current state of the orderbook."""
    try:
        orderbook = api.get_orderbook(TRADING_PAIR, limit=depth)
        
        print("\n=== Current Orderbook State ===")
        print("Top Bids:")
        for price, quantity in orderbook['bids'][:depth]:
            print(f"  Price: {float(price):.8f}, Quantity: {float(quantity):.4f}")
            
        print("\nTop Asks:")
        for price, quantity in orderbook['asks'][:depth]:
            print(f"  Price: {float(price):.8f}, Quantity: {float(quantity):.4f}")
        print("=============================\n")
        
    except Exception as e:
        print(f"Error getting orderbook: {e}")

def test_cooldown_taker():
    # Initialize API client
    api = BinanceAPI(
        api_key=BINANCE_API_KEY,
        api_secret=BINANCE_API_SECRET,
        use_testnet=USE_TESTNET
    )
    
    # Create and start cooldown taker strategy
    strategy = CooldownTakerStrategy(api)
    
    try:
        print("Starting cooldown taker strategy...")
        print("\nInitial orderbook state:")
        print_orderbook_state(api)
        
        # Override the _place_taker_order method to add logging
        original_place_order = strategy._place_taker_order
        
        def enhanced_place_order():
            print("\n=== Before Placing Order ===")
            print_orderbook_state(api)
            
            # Place the order
            original_place_order()
            
            # Wait a moment for the order to be processed
            time.sleep(1)
            
            print("\n=== After Placing Order ===")
            print_orderbook_state(api)
            print("===========================\n")
        
        # Replace the method
        strategy._place_taker_order = enhanced_place_order
        
        # Start the strategy
        strategy.start()
        
        # Let it run for 2 minutes
        time.sleep(120)
        
    except KeyboardInterrupt:
        print("\nStopping cooldown taker strategy...")
    finally:
        strategy.stop()
        print("\nFinal orderbook state:")
        print_orderbook_state(api)
        print("Strategy stopped")

if __name__ == "__main__":
    test_cooldown_taker() 