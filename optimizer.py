"""
optimizer.py — Portfolio optimizer for GW2 Trading Post flipping.
Given fitted Weibull models + current prices, recommends optimal buy quantities.

Two modes:
  - 'greedy': fast heuristic, sorts by expected profit/gold
  - 'lp': scipy linear program (no cardinality constraint)
"""
import numpy as np
from scipy.optimize import linprog
from models import fill_probability


def build_opportunities(models, prices, time_horizon_days=1,
                         min_margin=0.05, min_fill_prob=0.0):
    """Build list of tradeable items with current prices and fill probs.

    Args:
        models: dict {item_name: {lambda_, rho_, ...}}
        prices: dict {item_id: {buy_price, sell_price, buy_qty, sell_qty}}
        time_horizon_days: expected holding period
        min_margin: minimum (sell-buy)/buy
        min_fill_prob: minimum fill probability

    Returns:
        list of dicts sorted by expected_profit_per_gold descending
    """
    opportunities = []
    for item_id_str, p in prices.items():
        # match by item_id — we need name mapping
        # For now, use item_id as key; name mapping comes from GW2 API
        buy_price = p['buy_price']
        sell_price = p['sell_price']
        buy_qty = p['buy_qty']

        if buy_price <= 0 or sell_price <= 0:
            continue

        margin = (sell_price - buy_price) / buy_price
        if margin < min_margin:
            continue

        # Find matching model (try both int and str keys)
        item_id = int(item_id_str)
        model = models.get(str(item_id)) or models.get(item_id)
        if model is None:
            prob = 0.5  # default if no model fitted
        else:
            prob = fill_probability(
                model['lambda_'], model['rho_'],
                time_horizon_days, quantity=1
            )

        if prob < min_fill_prob:
            continue

        profit_per_unit = sell_price - buy_price
        expected_profit_per_gold = (profit_per_unit * prob) / buy_price

        opportunities.append({
            'item_id': item_id,
            'buy_price': buy_price,
            'sell_price': sell_price,
            'margin': margin,
            'fill_prob': prob,
            'profit_per_unit': profit_per_unit,
            'expected_profit_per_gold': expected_profit_per_gold,
            'max_qty': min(buy_qty, 250),  # cap per item
        })

    opportunities.sort(key=lambda x: x['expected_profit_per_gold'], reverse=True)
    return opportunities


def greedy_allocate(opportunities, budget_gold, max_items=50):
    """Greedy allocation: buy best items until budget exhausted.

    Returns dict: {item_id: quantity}
    """
    budget_copper = budget_gold * 10000
    allocations = {}
    items_used = 0

    for opp in opportunities:
        if items_used >= max_items:
            break
        max_afford = budget_copper // opp['buy_price']
        qty = min(max_afford, opp['max_qty'])
        if qty <= 0:
            continue
        cost = qty * opp['buy_price']
        budget_copper -= cost
        allocations[opp['item_id']] = qty
        items_used += 1

    return allocations


def lp_allocate(opportunities, budget_gold):
    """Linear program: maximize expected profit subject to budget.

    No cardinality constraint — use greedy if you need item limits.
    Uses scipy.optimize.linprog (simplex/interior-point).

    Returns dict: {item_id: quantity}
    """
    n = len(opportunities)
    if n == 0:
        return {}

    # Objective: maximize expected_profit (profit × prob)
    c = [-opp['profit_per_unit'] * opp['fill_prob'] for opp in opportunities]

    # Budget constraint: Σ(buy_price × qty) ≤ budget
    A_ub = [[opp['buy_price'] for opp in opportunities]]
    b_ub = [budget_gold * 10000]

    # Bounds: 0 ≤ qty_i ≤ max_qty_i
    bounds = [(0, opp['max_qty']) for opp in opportunities]

    result = linprog(c, A_ub=A_ub, b_ub=b_ub, bounds=bounds, method='highs')

    if not result.success:
        return {}

    allocations = {}
    for i, opp in enumerate(opportunities):
        qty = int(result.x[i])
        if qty > 0:
            allocations[opp['item_id']] = qty

    return allocations


def optimize(models, prices, budget_gold=1000, time_horizon_days=1,
             min_margin=0.05, min_fill_prob=0.0, max_items=50, mode='greedy'):
    """Main entry point. Returns allocation + summary stats."""
    opps = build_opportunities(models, prices, time_horizon_days,
                                min_margin, min_fill_prob)

    if mode == 'lp':
        alloc = lp_allocate(opps, budget_gold)
    else:
        alloc = greedy_allocate(opps, budget_gold, max_items)

    # Build summary
    summary = []
    total_cost = 0
    total_expected_profit = 0
    for opp in opps:
        qty = alloc.get(opp['item_id'], 0)
        if qty == 0:
            continue
        cost = qty * opp['buy_price']
        expected_profit = qty * opp['profit_per_unit'] * opp['fill_prob']
        total_cost += cost
        total_expected_profit += expected_profit
        summary.append({
            **opp,
            'quantity': qty,
            'cost_gold': cost / 10000,
            'expected_profit_gold': expected_profit / 10000,
        })

    return {
        'allocations': alloc,
        'summary': summary,
        'total_cost_gold': total_cost / 10000,
        'total_expected_profit_gold': total_expected_profit / 10000,
        'roi_percent': (total_expected_profit / total_cost * 100) if total_cost else 0,
        'items_selected': len(summary),
    }
