import os

PORT = int(os.environ.get("PORT", "8001"))
EXECUTION_MODE = os.environ.get("EXECUTION_MODE", "paper")  # paper | live
BROKER_BACKEND = os.environ.get("BROKER_BACKEND", "mt5")  # mt5

# MT5
MT5_PATH = os.environ.get("MT5_PATH", None)
MT5_LOGIN = os.environ.get("MT5_LOGIN", "")
MT5_PASSWORD = os.environ.get("MT5_PASSWORD", "")
MT5_SERVER = os.environ.get("MT5_SERVER", "MetaQuotes-Demo")
MT5_DEFAULT_LOTS = float(os.environ.get("MT5_DEFAULT_LOTS", "0.01"))

# Journal
JOURNAL_DIR = os.environ.get("JOURNAL_DIR", "app/journal")
DATA_DIR = os.environ.get("DATA_DIR", "data")
