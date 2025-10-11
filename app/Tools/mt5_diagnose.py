"""
MT5 Diagnostic Utility
----------------------
Run this script to verify MetaTrader5 Python API is properly installed,
linked to the MT5 terminal, and can access account data.

Usage:
    python app/tools/mt5_diagnose.py
"""

import os
import platform
import sys
from typing import Any

from dotenv import load_dotenv

print("=== MetaTrader 5 Diagnostic ===")

# -------------------------------------------------------------
# 1️⃣ Load optional environment (if present)
# -------------------------------------------------------------
env_file = os.getenv("MT5_ENV", "app/env/.merged/env.FX.merged.env")
if os.path.exists(env_file):
    load_dotenv(env_file)
    print(f"Loaded environment: {env_file}")
else:
    print(f"No env file found at {env_file}, continuing with defaults.")

# -------------------------------------------------------------
# 2️⃣ Verify Python and OS
# -------------------------------------------------------------
print(f"Python version : {platform.python_version()} ({platform.architecture()[0]})")
print(f"Platform       : {platform.system()} {platform.release()}")

if platform.system().lower() != "windows":
    print("❌ MT5 only supports Windows. Please run on Windows with terminal64.exe installed.")
    sys.exit(1)

# -------------------------------------------------------------
# 3️⃣ Import MetaTrader5
# -------------------------------------------------------------
try:
    import MetaTrader5 as _mt5

    mt5: Any = _mt5  # type: ignore
except Exception as e:
    print(f"❌ Cannot import MetaTrader5 module: {e}")
    print("   → Try: pip install MetaTrader5")
    sys.exit(1)

print("✅ MetaTrader5 module imported.")

# -------------------------------------------------------------
# 4️⃣ Show module attributes (sanity check)
# -------------------------------------------------------------
has_funcs = [
    f for f in ("initialize", "version", "account_info", "history_select") if hasattr(mt5, f)
]
print(f"Available API functions: {has_funcs}")
if "initialize" not in has_funcs:
    print("❌ 'initialize' not found. MT5 module backend failed to load.")
    sys.exit(1)

# -------------------------------------------------------------
# 5️⃣ Attempt initialization
# -------------------------------------------------------------
MT5_PATH = os.getenv("MT5_PATH", r"C:\Program Files\MetaTrader 5\terminal64.exe")
MT5_LOGIN = int(os.getenv("MT5_LOGIN", "0"))
MT5_PASSWORD = os.getenv("MT5_PASSWORD")
MT5_SERVER = os.getenv("MT5_SERVER")

print(f"Using terminal path: {MT5_PATH}")

ok = False
try:
    if MT5_PATH and os.path.exists(MT5_PATH):
        ok = mt5.initialize(MT5_PATH, login=MT5_LOGIN, password=MT5_PASSWORD, server=MT5_SERVER)
    else:
        ok = mt5.initialize()
except Exception as e:
    print(f"❌ Exception during initialize(): {e}")

if not ok:
    print(f"❌ Initialization failed: {getattr(mt5, 'last_error', lambda: 'unknown')()}")
    print("   → Ensure terminal64.exe path and credentials are correct.")
    sys.exit(1)

print("✅ MT5 initialize() succeeded.")

# -------------------------------------------------------------
# 6️⃣ Connection info
# -------------------------------------------------------------
ver = mt5.version()
print(f"MT5 version    : {ver}")

acc = mt5.account_info()
if not acc:
    print("⚠️  Connected but no active account session (demo/login missing).")
else:
    print(f"✅ Account Info : Login={acc.login}, Server={acc.server}, Balance={acc.balance:.2f}")

# -------------------------------------------------------------
# 7️⃣ Basic data test (optional)
# -------------------------------------------------------------
try:
    symbols = mt5.symbols_get()
    print(f"✅ Retrieved {len(symbols)} symbols.")
except Exception as e:
    print(f"⚠️ Could not retrieve symbols: {e}")

# -------------------------------------------------------------
# 8️⃣ Shutdown cleanly
# -------------------------------------------------------------
mt5.shutdown()
print("✅ MT5 shutdown() OK")
print("=== Diagnostic complete ===")
