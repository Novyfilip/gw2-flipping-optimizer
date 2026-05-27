# -*- coding: utf-8 -*-
"""
Created on Mon Dec 15 10:51:42 2025

@author: filip
"""
import numpy as np
import pandas as pd
buy_data_path = 'data/buy_history_buy_history_2025-09-16_to_2025-12-15.csv'
sell_data_path = "data/sell_orders/sell_history_2025-09-16_to_2025-12-15.csv"

buys = pd.read_csv(buy_data_path)
sells = pd.read_csv(sell_data_path)
buys.head()