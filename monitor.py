import argparse
from utils.binance_api import BinanceAPI
from config import BINANCE_API_KEY, BINANCE_API_SECRET, USE_TESTNET


# how much UNI we have bought so far
# average price of UNI so far
# total value of UNI we need to buy
# remaining cost of UNI 

class TradeMonitoring:
    def __init__(self, client: BinanceAPI, target_uni_amount: float):
        self.client = client
        self.target_uni_amount = target_uni_amount
        self.uni_bought = 0.0
        self.total_cost = 0.0
        self.uni_average_price = 0.0

    def record_fill(self, qty: float, price: float):  # For recording fills
        self.uni_bought += qty
        self.total_cost += qty * price
        if self.uni_bought > 0:
            self.uni_average_price = self.total_cost / self.uni_bought


    def get_uni_balance(self) -> float: #for getting UNI balance
        try:
            balances = self.client.get_asset_balance(asset='UNI')
            if balances:
                return float(balances['free']) + float(balances['locked'])
        except Exception as e:
            print(f"Error fetching UNI balance: {e}")
        return 0.0

    def remaining_uni_to_buy(self) -> float:
        return max(0.0, self.target_uni_amount - self.uni_bought)

    def remaining_cost(self, current_price: float) -> float:
        return self.remaining_uni_to_buy() * current_price

    def summary(self, current_price: float):
        with self.lock:
            print("="*40)
            print(f"UNI bought so far:      {self.uni_bought:.4f}")
            print(f"Average price:         {self.uni_average_price:.4f} USDT")
            print(f"UNI balance (Binance): {self.get_uni_balance():.4f}")
            print(f"Remaining UNI to buy:  {self.remaining_uni_to_buy():.4f}")
            print(f"Remaining cost (est.): {self.remaining_cost(current_price):.2f} USDT")
            print("="*40)

if __name__ == "__main__":
    api = BinanceAPI(
        api_key=BINANCE_API_KEY,
        api_secret=BINANCE_API_SECRET,
        use_testnet=USE_TESTNET
    )
    parser = argparse.ArgumentParser(description="UNI Accumulation Monitor")
    parser.add_argument("--target-uni", type=float, help="Target UNI amount to accumulate")
    args = parser.parse_args()

    if args.target_uni is not None:
        TARGET_UNI = args.target_uni
    else:
        TARGET_UNI = float(input("Enter target UNI amount to accumulate: "))

    monitor = TradeMonitoring(api, TARGET_UNI)




