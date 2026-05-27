"""
optimizer.py — Portfolio optimizer for GW2 Trading Post flipping.

Improved formulation:
  Maximize: Σ (sell_i - buy_i) × fill_prob_i × qty_i
  Subject to:
    Σ (buy_i × qty_i) ≤ budget
    qty_i ≤ market_depth_i (available at current buy price)
    qty_i ≤ expected_sales_in_horizon (don't buy what won't sell)
    buy_i × qty_i ≥ min_order_gold (for allocated items)
    qty_i ∈ {0, 1, 2, ...}
"""
import numpy as np
from scipy.optimize import linprog
from models import fill_probability


def build_opportunities(models, prices, time_horizon_days=1,
                         min_margin=0.05, min_fill_prob=0.0,
                         min_order_gold=0.01):
    """Build tradeable item list from current prices + fill models.

    Args:
        models: dict {item_id or item_name: {lambda_, rho_, ...}}
        prices: dict {item_id: {buy_price, sell_price, buy_qty, sell_qty}}
        time_horizon_days: how long you're willing to hold
        min_margin: minimum (sell-buy)/buy (e.g., 0.05 = 5%)
        min_fill_prob: minimum P(fill within horizon)
        min_order_gold: minimum position value in gold (skip pennies)

    Returns:
        list of dicts sorted by expected_profit_per_gold desc
    """
    min_order_copper = min_order_gold * 10000
    opportunities = []

    for item_id_str, p in prices.items():
        buy_price = p['buy_price']
        sell_price = p['sell_price']
        buy_qty = p['buy_qty']

        if buy_price <= 0 or sell_price <= 0:
            continue

        # Skip items where max position value < minimum
        if buy_price * buy_qty < min_order_copper:
            continue

        margin = (sell_price - buy_price) / buy_price
        if margin < min_margin:
            continue

        # Look up fill model
        item_id = int(item_id_str)
        model = models.get(str(item_id)) or models.get(item_id)
        if model is None:
            prob = 0.5  # default: no data yet
        else:
            prob = fill_probability(
                model['lambda_'], model['rho_'],
                time_horizon_days, quantity=1
            )

        if prob < min_fill_prob:
            continue

        profit_per_unit = sell_price - buy_price

        # Cap quantity: don't buy more than market can absorb in the horizon
        # Low fill_prob items get stricter caps (Svaard's recipes: prob=0.1 → cap at 10%)
        sellable_in_horizon = max(1, int(buy_qty * prob))
        effective_max_qty = min(buy_qty, sellable_in_horizon, 250)

        expected_profit_per_gold = (profit_per_unit * prob) / buy_price

        opportunities.append({
            'item_id': item_id,
            'buy_price': buy_price,
            'sell_price': sell_price,
            'margin': margin,
            'fill_prob': prob,
            'profit_per_unit': profit_per_unit,
            'expected_profit_per_gold': expected_profit_per_gold,
            'max_qty': effective_max_qty,
            'market_depth': buy_qty,
        })

    opportunities.sort(key=lambda x: x['expected_profit_per_gold'], reverse=True)
    return opportunities


def greedy_allocate(opportunities, budget_gold, max_items=50,
                     min_order_gold=0.01):
    """Greedy allocation: buy best items until budget exhausted.

    Immediately removes items that fall below min_order_gold after allocation.
    """
    budget_copper = budget_gold * 10000
    min_order_copper = min_order_gold * 10000
    allocations = {}

    for opp in opportunities:
        if len(allocations) >= max_items:
            break

        max_afford = budget_copper // opp['buy_price']
        qty = min(max_afford, opp['max_qty'])

        # Skip if we can't afford even 1 unit
        if qty <= 0:
            continue

        # Skip if position value below minimum
        if qty * opp['buy_price'] < min_order_copper:
            continue

        cost = qty * opp['buy_price']
        budget_copper -= cost
        allocations[opp['item_id']] = qty

    return allocations


def lp_allocate(opportunities, budget_gold):
    """Linear program via scipy. No cardinality or min-order constraints.

    Use greedy for practical recommendations; LP for sanity-checking totals.
    """
    n = len(opportunities)
    if n == 0:
        return {}

    c = [-opp['profit_per_unit'] * opp['fill_prob'] for opp in opportunities]
    A_ub = [[opp['buy_price'] for opp in opportunities]]
    b_ub = [budget_gold * 10000]
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
             min_margin=0.05, min_fill_prob=0.0, max_items=50,
             min_order_gold=0.01, mode='greedy'):
    """Main entry point.

    Args:
        budget_gold: available gold to deploy
        time_horizon_days: how long before you want items sold
        min_margin: minimum profit margin (fraction, e.g. 0.05 = 5%)
        min_fill_prob: minimum P(sells within horizon)
        max_items: max distinct items (clicking limit)
        min_order_gold: minimum position value per item (skip pennies)
        mode: 'greedy' (recommended) or 'lp' (experimental)

    Returns:
        dict with allocations, summary table, totals
    """
    opps = build_opportunities(models, prices, time_horizon_days,
                                min_margin, min_fill_prob, min_order_gold)

    if mode == 'lp':
        alloc = lp_allocate(opps, budget_gold)
    else:
        alloc = greedy_allocate(opps, budget_gold, max_items, min_order_gold)

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
