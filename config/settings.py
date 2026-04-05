from datetime import date


# ---------------------------------------------------------------------------
# Market
# ---------------------------------------------------------------------------

MARKET = "TW"          # Taiwan Stock Exchange
CURRENCY = "TWD"
TRADING_DAYS_PER_YEAR = 252


# ---------------------------------------------------------------------------
# Default date range
# ---------------------------------------------------------------------------

# How far back to fetch data when no explicit start_date is given
DEFAULT_START_DATE: date = date(2020, 1, 1)
DEFAULT_END_DATE: date = date.today()


# ---------------------------------------------------------------------------
# Universe
# ---------------------------------------------------------------------------

# Seed list of stocks to analyse; extend as needed
DEFAULT_STOCK_IDS: list[str] = [
    "2330",  # TSMC
    "2317",  # Foxconn
    "2454",  # MediaTek
    "2382",  # Quanta Computer
    "2308",  # Delta Electronics
]


# ---------------------------------------------------------------------------
# Signal thresholds (placeholders — tune in Phase 2)
# ---------------------------------------------------------------------------

# Moving average crossover
MA_SHORT_WINDOW: int = 5     # days
MA_LONG_WINDOW: int = 20     # days

# RSI
RSI_WINDOW: int = 14
RSI_OVERSOLD: float = 30.0
RSI_OVERBOUGHT: float = 70.0

# Volume surge: flag if volume exceeds N× the rolling average
VOLUME_SURGE_MULTIPLIER: float = 2.0
VOLUME_SURGE_WINDOW: int = 20  # days

# Minimum price filter (skip penny / delisted stocks)
MIN_CLOSE_PRICE: float = 5.0   # TWD


# ---------------------------------------------------------------------------
# Data storage
# ---------------------------------------------------------------------------

# Relative to project root; override in tests by passing cache_dir explicitly
CACHE_DIR: str = ".cache"
