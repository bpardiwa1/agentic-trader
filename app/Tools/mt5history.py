from datetime import datetime
from typing import Any

import MetaTrader5 as _mt5
import MetaTrader5 as mt5
import pandas as pd

mt5: Any = _mt5  # type: ignore


pd.set_option("display.max_columns", 500)  # number of columns to be displayed
pd.set_option("display.width", 1500)  # max table width to display
# display data on the MetaTrader 5 package
print("MetaTrader5 package author: ", mt5.__author__)
print("MetaTrader5 package version: ", mt5.__version__)
print()
# establish connection to the MetaTrader 5 terminal
if not mt5.initialize():
    print("initialize() failed, error code =", mt5.last_error())
    quit()

# get the number of orders in history
from_date = datetime(2025, 10, 1)
print("=========================")
print("From Date:", from_date)
print("=========================")
to_date = datetime.now()
print("To Date:", to_date)
print("=========================")
total = mt5.history_orders_total(from_date, to_date)
history_orders = mt5.history_orders_get(from_date, to_date, group="*USD*")
if history_orders == None:
    print(f'No history orders with group="*USD*", error code={mt5.last_error()}')
elif len(history_orders) > 0:
    print(f'history_orders_get({from_date}, {to_date}, group="*USD*")={len(history_orders)}')
print()

# display all historical orders by a position ticket
position_id = 50565002
position_history_orders = mt5.history_orders_get(position=position_id)
if position_history_orders == None:
    print(f"No orders with position #{position_id}")
    print("error code =", mt5.last_error())
elif len(position_history_orders) > 0:
    print(f"Total history orders on position #{position_id}: {len(position_history_orders)}")
    # display all historical orders having a specified position ticket
    for position_order in position_history_orders:
        print(position_order)
    print()
    # display these orders as a table using pandas.DataFrame
    df = pd.DataFrame(
        list(position_history_orders), columns=position_history_orders[0]._asdict().keys()
    )
    df.drop(
        [
            "time_expiration",
            "type_time",
            "state",
            "position_by_id",
            "reason",
            "volume_current",
            "price_stoplimit",
            "sl",
            "tp",
        ],
        axis=1,
        inplace=True,
    )
    df["time_setup"] = pd.to_datetime(df["time_setup"], unit="s")
    df["time_done"] = pd.to_datetime(df["time_done"], unit="s")
    print(df)

# shut down connection to the MetaTrader 5 terminal
mt5.shutdown()
