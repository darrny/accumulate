# ANSI color codes for terminal output
class Colors:
    # Basic colors
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    WHITE = '\033[97m'
    
    # Bold colors
    BOLD = '\033[1m'
    BOLD_RED = '\033[1;91m'
    BOLD_GREEN = '\033[1;92m'
    BOLD_YELLOW = '\033[1;93m'
    BOLD_BLUE = '\033[1;94m'
    BOLD_MAGENTA = '\033[1;95m'
    BOLD_CYAN = '\033[1;96m'
    BOLD_WHITE = '\033[1;97m'
    
    # Custom colors
    PINK = '\033[38;5;218m'  # Light pink
    GOLDEN = '\033[38;5;220m'  # Golden yellow
    
    # Reset
    ENDC = '\033[0m'

# Strategy colors mapping
STRATEGY_COLORS = {
    'shadow_bid': Colors.CYAN,
    'cooldown_taker': Colors.PINK,
    'big_fish': Colors.GOLDEN
} 