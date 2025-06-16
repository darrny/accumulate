import logging
import time
import subprocess
import sys

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def run_test(test_file: str) -> bool:
    """
    Run a test file and return True if successful.
    """
    logger.info(f"\n{'='*50}")
    logger.info(f"Running {test_file}...")
    logger.info(f"{'='*50}\n")
    
    try:
        result = subprocess.run([sys.executable, test_file], check=True)
        logger.info(f"\n{test_file} completed successfully")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"\n{test_file} failed with error: {e}")
        return False
    except Exception as e:
        logger.error(f"\nError running {test_file}: {e}")
        return False

def main():
    """
    Run all test files in sequence.
    """
    test_files = [
        'test_binance_api.py',
        'test_shadow_bid.py',
        'test_cooldown_taker.py',
        'test_big_fish.py'
    ]
    
    success = True
    for test_file in test_files:
        if not run_test(test_file):
            success = False
            logger.error(f"\nStopping test sequence due to failure in {test_file}")
            break
        time.sleep(2)  # Small delay between tests
    
    if success:
        logger.info("\nAll tests completed successfully!")
    else:
        logger.error("\nTest sequence failed!")
        sys.exit(1)

if __name__ == "__main__":
    main() 