# Crypto Trading Bot for Binance

A robust, multi-strategy crypto trading bot for Binance, written in Python. This bot supports dynamic strategy toggling, real-time monitoring, and clean logging. It interacts with Binance via both REST and WebSocket APIs, and is designed for reliability, flexibility, and ease of use.

## Features
- **Multiple Strategies:**
  - Shadow Bid
  - Cooldown Taker
  - Big Fish
- **Dynamic Strategy Toggling:** Enable/disable strategies at runtime via `config_strategies.py`.
- **WebSocket & REST API:** Real-time orderbook, trade, and account updates.
- **Robust Logging:** Consistent, color-coded, single-line log output.
- **Session Tracking:** Tracks balances, average entry price, and session stats.
- **Safe Shutdown:** Cancels all open orders and closes connections on exit or target reached.

## Requirements
- Python 3.8+
- Binance account (API key/secret)

Install dependencies:
```bash
pip install -r requirements.txt
```

## Configuration

### 1. `config.py`
Set your Binance API credentials, trading pair, and strategy parameters in `config.py`:

```python
USE_TESTNET = False  # Set to True for Binance testnet

# API Keys
TESTNET_API_KEY = "..."
TESTNET_API_SECRET = "..."
PROD_API_KEY = "..."
PROD_API_SECRET = "..."

# Trading
TRADING_PAIR = "UNIFDUSD"
BASE = "UNI"
QUOTE = "FDUSD"
MAX_PRICE = 7.70
QUOTE_PRICE = 7.85182
TARGET_QUANTITY = 100

# Strategy Configurations
SHADOW_BID = {
    'cooldown_time': 16,  # Base time (in seconds) to wait between placing orders
    'jitter': 3,  # Random time (in seconds) to add/subtract from cooldown for randomization
    'price_multiplier': 0,  # How far below best bid to place our order (0 = same price)
    'order_size_percentage': 0.01,  # Order size as percentage of target (10%)
}

COOLDOWN_TAKER = {
    'min_cooldown': 16,  # Minimum time (in seconds) to wait between taking orders
    'jitter': 3,  # Random time (in seconds) to add/subtract from cooldown for randomization
    'max_ask1_quantity_percentage': 0.001,  # Maximum quantity in best ask as percentage of remaining target (0.1%)
    'order_size_percentage': 0.1,  # Order size as percentage of target (10%)
}

BIG_FISH = {
    'cooldown_time': 16,  # Base time (in seconds) to wait between analyzing orderbook
    'jitter': 3,  # Random time (in seconds) to add/subtract from cooldown for randomization
    'min_volume_percentage': 0.05,  # Minimum volume as percentage of target (5%)
    'max_orders_to_analyze': 20,  # How many orders deep to look in the orderbook for big fish
}
```

### 2. `config_strategies.py`
Toggle which strategies are enabled at startup and runtime:
```python
SHADOW_BID = True
COOLDOWN_TAKER = False
BIG_FISH = True
```
Set to `True` to enable, `False` to disable. The bot will start only enabled strategies and can dynamically enable/disable them while running.

## Usage

### Start the Trading Bot
```bash
python monitor.py
```
- The bot will read `config_strategies.py` and start only enabled strategies.
- Strategies are started 4 seconds apart for safety.
- The bot will monitor progress, log all actions, and shut down safely when the target is reached or on interruption.

### Toggling Strategies at Runtime
- Edit `config_strategies.py` while the bot is running.
- The bot checks this file every 10 seconds and will start/stop strategies accordingly.

## Utility Scripts

### Account Info
Get a summary of your Binance account, balances, open orders, and recent trades:
```bash
python account_info.py
```
Add `--cancel-orders` to cancel all open orders for the trading pair.

### Sell Holdings
Sell a specified amount of your holdings at market price:
```bash
python sell_holdings.py <quantity>
```

## Strategies
- **Shadow Bid:** Places limit orders at or near the best bid, aiming to accumulate at favorable prices.
- **Cooldown Taker:** Places market orders at intervals, with configurable cooldown and order size.
- **Big Fish:** Looks for large sell walls ("big fish") in the orderbook and places limit orders to take advantage.

Strategy parameters are configured in `config.py`.

## Logging
- All logs are timestamped and color-coded for clarity.
- No multi-line or leading-newline log messages.
- Session summary and progress are logged throughout.

## Safety & Shutdown
- On reaching the target, interruption, or error, the bot cancels all open orders, stops all strategies, and closes all connections cleanly.

## Directory Structure
```
accumulate/
  monitor.py              # Main entrypoint
  config.py               # Main configuration
  config_strategies.py    # Strategy toggling
  requirements.txt        # Dependencies
  account_info.py         # Account info utility
  sell_holdings.py        # Sell utility
  strategies/             # All strategy implementations
  utils/                  # Binance API and color utilities
```

## License
This project is for educational and research purposes. Use at your own risk. 