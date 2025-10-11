import MetaTrader5 as mt5

mt5.initialize()
info = mt5.symbol_info("NAS100.s")
print(info)
