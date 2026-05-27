# GW2 Trading Post Optimizer — Plan

## Core Data Advantage

Public GW2 API + sites like gw2bltc only expose **current listing prices and volumes**. Everyone has this.

This app's edge: **fill velocity data**. How long does a specific item take to sell? In what batch sizes? Nobody publishes this. It comes exclusively from your completed transaction history via `/v2/commerce/transactions/history/` (last 90 days, API-key scoped).

**Daily price tracker:** public data — buy/sell listing prices and volumes  
**Transaction fetcher:** private data — actual fill times and quantities  
**Weibull models:** `P(sells within T days | item)` — the edge  
**Optimizer:** budget + horizon → optimal buy list with real fees

## ML Pipeline (now automated)

```
Daily GitHub Action
  ├── track_prices.py          → item_prices table (price history)
  └── fetch_transaction_history.py → sell_history CSVs (fill times)

Manual (when enough data accumulated):
  python fit_models.py          → data/item_fill_models.json (Weibull params)

Flask /plan route:
  loads models → loads prices → runs optimizer → buy recommendations
```

## Architecture

```
tp.py                    Flask: dashboard (/), recommender (/plan), auth
├── orders.py            Order persistence & fill detection
├── db.py                SQLite: users, open_orders, fills, item_prices
├── track_prices.py      Daily price snapshot (catalog + open orders)
├── fetch_transaction_history.py  Completed transaction CSV export
├── fit_models.py        Fit Weibull models from sell history → JSON
├── models.py            Weibull: fit, load, fill_probability()
├── optimizer.py         Greedy allocation with fee-aware profit calc
├── users.py             Auth (PBKDF2)
├── favorites.py         Favorites stub
│
├── data/my_trading_items.csv     760+ items (id, name, volume)
├── data/sell_orders/             Historical sell transactions (fill times)
├── data/buy_orders/              Historical buy transactions
├── data/item_fill_models.json    Fitted Weibull params (from fit_models.py)
│
├── fill_model_v_batchFillProb.ipynb  Notebook for explorator y modeling
├── fill_model_v0_1.ipynb, v0_2.ipynb  Earlier iterations
├── Optimizer.ipynb               LP skeleton (replaced by optimizer.py)
├── item catalogue.py             gw2efficiency data analysis utility
│
├── templates/
│   ├── index.html     Dashboard with buy/sell/delivery tables
│   ├── plan.html      Recommender: budget/horizon → buy list
│   ├── favorites.html Stub
│   └── register.html  User registration
│
└── .github/workflows/daily-track.yml  Daily price + transaction collection
```

## Optimizer Details

**Fee structure (now correct):**
- Buy: no fee
- Sell: 5% listing fee + 10% exchange fee = 15% total
- Net profit = sell_price × 0.85 - buy_price

**Fill probability (two-tier):**
1. Weibull model from `item_fill_models.json` (if fitted)
2. Volume-based heuristic: `P(fill) = min(0.9, sell_volume / 500)` with time horizon modifier

**Quantity modeling (to be implemented):**
- 1 unit vs 100 units fill at different rates
- Need per-item quantity bucket models
- Currently uses `sellable_in_horizon = max(1, sell_volume × fill_prob)`

## What's Left

### 1. Run fit_models.py once enough sell history accumulates
- Needs multiple CSV files with varied fill times
- `python fit_models.py --min-obs 5`
- Then optimizer switches from heuristic to real Weibull predictions

### 2. Quantity effects
- Currently placeholder `quantity_factor` in models.py
- Needs Weibull regression with quantity as covariate
- Or separate models per quantity bucket

### 3. /history page
- Price trends over time
- Portfolio growth chart
- Fill rate tracker

### 4. Favorites UI

## Setup

```
conda activate dl-env
pip install flask requests python-dotenv pandas scipy lifelines
python track_prices.py    # first price snapshot
python tp.py              # start dashboard
```

After accumulating sell history:
```
python fit_models.py
```
