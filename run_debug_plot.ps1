# Gold, 300 bars on M15, show last 120 candles
python debug_plot.py --symbol XAUUSD-ECNc --tf M15 --bars 300 --tail 120

# EURUSD
python debug_plot.py --symbol EURUSD-ECNc --tf M15 --bars 300 --tail 120

# Save PNGs instead of just showing
python debug_plot.py --symbol XAUUSD-ECNc --tf M15 --save
