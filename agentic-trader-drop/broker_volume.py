from app.brokers import mt5_client

print(mt5_client.symbol_info_dict("NAS100.S"))
