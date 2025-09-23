# debug_bars.py
from app.market.data import get_rates

# Fetch last 300 bars of XAUUSD and EURUSD on M15
df_xau = get_rates("XAUUSD-ECNc", "M15", 300)
df_eur = get_rates("EURUSD-ECNc", "M15", 300)

print("=== XAUUSD-ECNc M15 (last 5 bars) ===")
print(df_xau.tail())   # last 5 rows

print("\n=== EURUSD-ECNc M15 (last 5 bars) ===")
print(df_eur.tail())   # last 5 rows
