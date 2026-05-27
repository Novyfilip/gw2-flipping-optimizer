"""
fit_models.py — Fit Weibull survival models from sell history CSVs.

Reads data/sell_orders/*.csv (all files), fits WeibullFitter per item,
exports to data/item_fill_models.json.

Usage:
    python fit_models.py                    # fit from all sell history
    python fit_models.py --min-obs 5        # require 5+ observations

The optimizer then loads these models automatically via models.load_models().
"""
import pandas as pd
import numpy as np
import json
import glob
import os
from lifelines import WeibullFitter


def load_all_sell_history(data_dir='data/sell_orders'):
    """Load and concatenate all sell history CSVs."""
    files = glob.glob(os.path.join(data_dir, 'sell_history_*.csv'))
    if not files:
        print("No sell history files found in", data_dir)
        return pd.DataFrame()

    dfs = []
    for f in files:
        try:
            df = pd.read_csv(f)
            dfs.append(df)
        except Exception as e:
            print(f"  Skipping {f}: {e}")

    if not dfs:
        return pd.DataFrame()

    combined = pd.concat(dfs, ignore_index=True)
    combined = combined.drop_duplicates()
    print(f"Loaded {len(combined)} transactions from {len(dfs)} files")
    return combined


def fit_models(df, min_observations=3):
    """Fit Weibull distribution to time_to_fill_hours for each item.

    Returns dict keyed by item_name.
    """
    models = {}
    for item_name, group in df.groupby('item_name'):
        durations = group['time_to_fill_hours'].dropna()
        if len(durations) < min_observations:
            continue

        try:
            wf = WeibullFitter()
            wf.fit(durations)

            # Also get item_id for keying
            item_id = int(group['item_id'].iloc[0])

            models[str(item_id)] = {
                'item_id': item_id,
                'item_name': item_name,
                'lambda_': float(wf.lambda_),
                'rho_': float(wf.rho_),
                'n_observations': len(durations),
                'median_fill_hours': float(durations.median()),
                'mean_fill_hours': float(durations.mean()),
                'std_fill_hours': float(durations.std()),
            }
        except Exception as e:
            print(f"  Failed to fit {item_name}: {e}")

    return models


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--min-obs', type=int, default=3,
                        help='Minimum observations per item (default: 3)')
    args = parser.parse_args()

    print("Loading sell history...")
    df = load_all_sell_history()

    if df.empty:
        print("No sell history data. Run fetch_transaction_history.py first.")
        return

    print(f"Fitting Weibull models (min {args.min_obs} observations)...")
    models = fit_models(df, min_observations=args.min_obs)

    if not models:
        print("No items had enough observations. Need more sell history data.")
        return

    out_path = 'data/item_fill_models.json'
    with open(out_path, 'w') as f:
        json.dump(models, f, indent=2)

    # Summary
    print(f"\nFitted {len(models)} models → {out_path}")
    print(f"Top 10 by observations:")
    top = sorted(models.values(), key=lambda x: x['n_observations'], reverse=True)[:10]
    for m in top:
        print(f"  {m['item_name']}: {m['n_observations']} obs, "
              f"median={m['median_fill_hours']:.0f}h, "
              f"P(1d)={1 - np.exp(-(24/m['lambda_'])**m['rho_']):.0%}")


if __name__ == '__main__':
    main()
