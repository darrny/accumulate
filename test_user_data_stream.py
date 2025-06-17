import logging
from binance import ThreadedWebsocketManager
from config import USE_TESTNET, PROD_API_KEY, PROD_API_SECRET, PROD_ED_KEY
from utils.ed25519_auth import get_user_data_stream, close_user_data_stream

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def handle_user_data(message):
    """Handle incoming user data stream messages"""
    logger.info(f"Received user data: {message}")

def test_user_stream():
    """Test the user data stream connection"""
    try:
        logger.info("Starting user data stream test...")
        
        if USE_TESTNET:
            # Use ED25519 authentication for testnet
            logger.info("Using testnet with ED25519 authentication")
            user_stream = get_user_data_stream(handle_user_data)
            logger.info("Successfully connected to testnet user data stream")
            
            # Keep the script running for 30 seconds to receive some updates
            import time
            time.sleep(30)
            
            # Close the stream
            close_user_data_stream(user_stream)
            logger.info("Closed testnet user data stream")
        else:
            # Use regular authentication for production
            logger.info("Using production with regular authentication")
            twm = ThreadedWebsocketManager(
                api_key=PROD_API_KEY,
                api_secret=PROD_API_SECRET
            )
            twm.start()
            
            # Start user socket
            user_stream = twm.start_user_socket(handle_user_data)
            logger.info("Successfully connected to production user data stream")
            
            # Keep the script running for 30 seconds to receive some updates
            import time
            time.sleep(30)
            
            # Stop the WebSocket manager
            twm.stop()
            logger.info("Closed production user data stream")
            
    except Exception as e:
        logger.error(f"Error testing user data stream: {str(e)}")
        raise

if __name__ == "__main__":
    test_user_stream() 