"""
models.py — Weibull fill probability models for GW2 trading items.
Extracted from fill_model_v_batchFillProb.ipynb.
"""
import json
import numpy as np
from lifelines import WeibullFitter


def fit_item_models(df, min_observations=3):
    """Fit Weibull distribution to time_to_fill_hours for each item.

    Args:
        df: DataFrame with columns item_name, time_to_fill_hours
        min_observations: minimum completed transactions required per item

    Returns:
        dict: {item_name: {lambda_, rho_, n_observations, median_fill_hours, ...}}
    """
    item_distributions = {}
    for item_name, group in df.groupby('item_name'):
        if len(group) < min_observations:
            continue
        durations = group['time_to_fill_hours'].dropna()
        if len(durations) < min_observations:
            continue

        wf = WeibullFitter()
        wf.fit(durations)

        item_distributions[item_name] = {
            'item_name': item_name,
            'lambda_': float(wf.lambda_),
            'rho_': float(wf.rho_),
            'n_observations': len(durations),
            'median_fill_hours': float(durations.median()),
            'mean_fill_hours': float(durations.mean()),
            'std_fill_hours': float(durations.std()),
        }
    return item_distributions


def fill_probability(lambda_, rho_, time_horizon_days, quantity=1):
    """P(item fills within time_horizon_days) using Weibull CDF.

    F(t) = 1 - exp(-(t/lambda)^rho)

    Args:
        lambda_: scale parameter (hours)
        rho_: shape parameter
        time_horizon_days: time window in days
        quantity: batch size (applies diminishing-returns factor for >1)

    Returns:
        float between 0 and 1
    """
    time_horizon_hours = time_horizon_days * 24
    p_single = 1 - np.exp(-((time_horizon_hours / lambda_) ** rho_))

    if quantity > 1:
        quantity_factor = 1 / (1 + 0.05 * quantity)
        return p_single * quantity_factor

    return p_single


def load_models(path='data/item_fill_models.json'):
    """Load fitted Weibull parameters from JSON."""
    with open(path, 'r') as f:
        return json.load(f)


def save_models(models, path='data/item_fill_models.json'):
    """Save fitted parameters to JSON."""
    with open(path, 'w') as f:
        json.dump(models, f, indent=2)
