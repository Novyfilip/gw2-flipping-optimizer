# GW2 Trading Post Optimizer — Plan

## Core Data Advantage

The official GW2 API + sites like gw2bltc only expose **current listing prices and volumes**. Everyone has this.

This app's edge: **fill velocity data**. How long does a specific item take to sell? In what batch sizes? Nobody publishes this. It comes exclusively from your completed transaction history — either from gw2efficiency exports or the official `/v2/commerce/transactions/history/` endpoint (last 90 days, API-key scoped).

What you get: `time_to_fill_hours`, `quantity` per fill, `price` per fill. This feeds the Weibull survival models. Without it, any optimizer is just guessing from margins. With it, you know if an item *will actually sell* in your time horizon.

**Daily price tracker:** public data — buy/sell listing prices and volumes  
**Transaction fetcher:** private data — actual fill times and quantities  
**Weibull models:** `P(sells within T days | item, quantity)` — the edge

## Architecture

```
tp.py                    Flask: dashboard (/), recommender (/plan), auth
├── orders.py            Order persistence & fill detection
├── db.py                SQLite: users, open_orders, fills, item_prices
├── track_prices.py      Daily price snapshot for all known items
├── fetch_transaction_history.py  Completed transaction CSV export
├── models.py            Weibull: fit, load, fill_probability()
├── optimizer.py         Greedy + LP: budget → buy list
├── users.py             Auth (PBKDF2)
├── favorites.py         Favorites stub
│
├── data/my_trading_items.csv     760+ items (id, name, volume)
├── data/sell_orders/             Historical sell transactions (fill times)
├── data/buy_orders/              Historical buy transactions
│
├── templates/index.html    Dashboard
├── templates/plan.html     Recommender with budget/horizon controls
│
└── .github/workflows/daily-track.yml  (needs setup via GitHub web UI)
```

## What Works

- Dashboard: live orders, delivery box, gold totals (medal format)
- Recommender: budget + horizon → ranked buy list
- Price tracker: snapshots prices for all known items
- Order fill detection: quantity delta across polls

## What's Left

### 1. Run the notebook to fit Weibull models
- `fill_model_v_batchFillProb.ipynb` uses sell history CSVs
- Export fitted params → `data/item_fill_models.json`
- Currently optimizer uses default 0.5 fill_prob — fine for ranking, inaccurate for expected profit

### 2. Wire transaction history into the daily workflow
- `fetch_transaction_history.py` fetches last 50 completed transactions per type
- Add to the GitHub Action so it accumulates sell history automatically
- This builds the training data for Weibull models over time

## Modeling Fill Times (The Edge)

Every item has a right-skewed fill-time distribution. Most orders fill fast, but some orders sit for days or weeks. Weibull captures this shape.

### Quantity Effects

Cheap commodities (silk, Elder Wood, T5 mats) — 10 vs 250 units makes little difference to fill time. The market absorbs volume easily.

Expensive items (Zhed's Coat, legendary components, rare skins, dyes) — steep diminishing returns. 1 unit might sell in 2 hours. 10 units might take 2 weeks. The buyer pool is thin.

### Optimal Order Size

The ideal quantity per order is where **marginal expected profit per unit** starts dropping below alternative uses of capital:

```
For item X at quantity q:
  profit_per_unit = sell_price - buy_price
  fill_prob(q) = P(sells within T days | batch size q)
  expected_profit = profit_per_unit × q × fill_prob(q)

Optimal q = argmax expected_profit  (subject to budget)
```

For silk: optimal q might be capped by market depth (buy order volume), not fill probability — it always sells.
For Zhed's Coat: optimal q is where fill_prob drops below your threshold — the model tells you "buying 5 is smart, buying 20 is tying up capital for a week."

### Current State

- `calculate_fill_probability()` has a placeholder `quantity_factor = 1 / (1 + 0.05 × q)` — this is a guess
- The Weibull model in the notebook fits on individual transaction rows — each row is a single fill event with its own quantity
- **What's needed:** fit a Weibull regression with quantity as a covariate, or fit separate Weibull models per quantity bucket (1-5 units, 6-20, 21-50, 51+)
- This requires enough varied transaction data per item — the daily fetcher accumulates this over time

### 4. `/history` page
- Price trends over time (buy/sell/margin)
- Portfolio growth chart
- Fill rate tracker

### 5. Favorites UI

## Setup

```
conda activate dl-env
pip install flask requests python-dotenv pandas scipy lifelines
python track_prices.py    # first price snapshot
python tp.py              # start dashboard
```
