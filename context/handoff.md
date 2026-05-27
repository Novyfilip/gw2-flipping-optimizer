# Handoff — Session 2026-05-27

## What We Did

### Portfolio Site (filipnovy.dk)
- Replaced Flask-based site with clean static HTML/CSS
- Dark sepia + amber design (Claude-inspired)
- Updated CV, added project screenshots (AlgaeBot architecture, Neo4j graph, trading dashboard, rank proof)
- Pushed to `Novyfilip/Portfolio-Site`, live at filipnovy.dk via Render

### GW2 Trading Post Optimizer (gw2-flipping-optimizer)
- Recovered all files from git history after a bad force-push (remote URL mixup)
- Fixed critical optimizer bugs:
  - Profit now accounts for 15% GW2 fees (5% listing + 10% exchange)
  - Fill probability uses volume-based heuristic instead of flat 0.5 default
  - `track_prices.py` includes `my_trading_items.csv` catalog as fallback source
  - `/plan` budget shows available gold (wallet minus locked)
- Built the ML pipeline:
  - `fit_models.py` — standalone script to fit Weibull models from sell history
  - Daily GitHub Action now runs both price tracking AND transaction history
- Removed dead code, added error handling to dashboard
- Delivery box section now renders on dashboard
- `context/plan.md` — architecture doc, restored after git wipe

### Job Search
- Searched Denmark, Prague, Switzerland for AI/ML/NLP roles
- Created `/mnt/c/Users/filip/Desktop/jobs/job_leads.md` — 20 curated positions
- Filip applied to AccionLabs (Principal AI Researcher) — title is inflated, role is mid-level
- Drafted Czech email response for recruiter Predrag

## Current State of GW2 App

### Working
- Dashboard: live buy/sell orders, delivery box, gold totals (medal format)
- Recommender (`/plan`): budget + horizon → ranked buy list with real fees
- Price tracker: snapshots prices for all catalog items (760+) plus open orders
- Order fill detection: quantity delta → fills table with fees
- Daily GitHub Action: auto-collects prices + sell history (needs GW2_KEY secret set up via GitHub web UI at `github.com/Novyfilip/gw2-flipping-optimizer/actions/new`)

### To Finish
1. Set up the GitHub Action via web UI (the `.github/workflows/daily-track.yml` is committed, just needs the `GW2_KEY` secret)
2. After ~2 weeks of accumulated sell history: `python fit_models.py` → generates `data/item_fill_models.json`
3. Once models exist, the optimizer switches from volume heuristic to real Weibull predictions
4. Quantity effects: Weibull regression with batch size as covariate (currently placeholder)
5. `/history` page: price trends, portfolio growth
6. Favorites UI

## Key Files

```
Gw2 Flipping Optimizer/
├── tp.py                 Main Flask app
├── optimizer.py          Greedy allocator (fee-aware, volume heuristic)
├── models.py             Weibull functions (fit, load, probability)
├── track_prices.py       Daily price snapshot (run manually or via Action)
├── fetch_transaction_history.py  Export completed transactions
├── fit_models.py         Fit Weibull → JSON (run after accumulating data)
├── db.py                 SQLite schema
├── orders.py             Order persistence + fill detection
├── users.py              PBKDF2 auth
├── context/plan.md       Architecture overview
├── context/handoff.md    This file
└── .github/workflows/daily-track.yml
```

## Setup for Dev
```
conda activate dl-env
pip install flask requests python-dotenv pandas scipy lifelines
python track_prices.py    # first price snapshot
python tp.py              # localhost:5000 — dashboard, /plan
```

## Filip's Preferences
- Works in WSL but runs Python from Windows (conda dl-env)
- Never run git from WSL (lock file conflicts with Git Bash)
- Direct communication, no emojis, no basicsplaining
- Czech native, English C2, German B1-B2, Danish A2
- ADHD — uses structured docs/context files
- Concerned about professional optics (no "vibe coding" visible in public repos)
- Thesis: AlgaeBot GraphRAG (KONVENS 2026, under review)
- Currently interviewing: Deloitte GenAI (Prague), AccionLabs (Prague)
- Holds GW2 trading data from gw2efficiency — saved in data/ directory
