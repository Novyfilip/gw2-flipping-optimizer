"""
optimizer.py — Portfolio optimizer for GW2 Trading Post flipping.

GW2 fee structure:
  - Buy order: no fee
  - Sell order: 5% listing fee (non-refundable) + 10% exchange fee on sale
  - Net profit per unit: sell_price * 0.85 - buy_price

Fill probability sources (priority order):
  1. Weibull model from item_fill_models.json (if fitted)
  2. Volume-based heuristic: P(fill) = min(0.9, sell_volume / 500)
     High-volume items (500+ listed) → high probability
     Low-volume items (10 listed) → low probability
"""
import numpy as np
from scipy.optimize import linprog
from models import fill_probability


def estimate_fill_prob(sell_qty, time_horizon_days=1):
    """Volume-based fill probability when no Weibull model exists.

    Rationale: sell_qty is the number of units CURRENTLY listed at the lowest
    sell price. High sell_qty = liquid market = high fill probability.
    Sell_qty of 500+ → 0.9, 10 → 0.02. Scales linearly in between.
    Time horizon modifier: longer horizon → higher probability.
    """
    base = min(0.9, sell_qty / 500)
    # Diminishing returns for longer horizons
    horizon_factor = 1 - np.exp(-time_horizon_days / 3)
    return min(0.95, base + (1 - base) * horizon_factor * 0.5)


def net_profit_per_unit(buy_price, sell_price):
    """Real profit after GW2 fees.

    Buy: pay buy_price. Sell: receive sell_price minus 15% total fees.
    """
    return sell_price * 0.85 - buy_price


def build_opportunities(models, prices, time_horizon_days=1,
                         min_margin=0.05, min_fill_prob=0.0,
                         min_order_gold=0.01):
    """Build tradeable item list from current prices + fill models.

    Returns list sorted by expected_profit_per_gold descending.
    """
    min_order_copper = min_order_gold * 10000
    opportunities = []

    for item_id_str, p in prices.items():
        buy_price = p['buy_price']
        sell_price = p['sell_price']
        buy_qty = p['buy_qty']
        sell_qty = p['sell_qty']

        if buy_price <= 0 or sell_price <= 0:
            continue

        if buy_price * buy_qty < min_order_copper:
            continue

        # Margin on real (post-fee) profit
        profit = net_profit_per_unit(buy_price, sell_price)
        if profit <= 0:
            continue
        margin = profit / buy_price
        if margin < min_margin:
            continue

        # Fill probability: Weibull model > volume heuristic
        item_id = int(item_id_str)
        model = models.get(str(item_id)) or models.get(item_id)
        if model is not None:
            prob = fill_probability(
                model['lambda_'], model['rho_'],
                time_horizon_days, quantity=1
            )
        else:
            prob = estimate_fill_prob(sell_qty, time_horizon_days)

        if prob < min_fill_prob:
            continue

        expected_profit_per_gold = (profit * prob) / buy_price

        # Don't buy more than the market can absorb in the horizon
        sellable_in_horizon = max(1, int(sell_qty * prob))
        effective_max_qty = min(buy_qty, sellable_in_horizon, 250)

        opportunities.append({
            'item_id': item_id,
            'buy_price': buy_price,
            'sell_price': sell_price,
            'margin': margin,
            'fill_prob': prob,
            'profit_per_unit': profit,
            'expected_profit_per_gold': expected_profit_per_gold,
            'max_qty': effective_max_qty,
            'market_depth': buy_qty,
            'sell_volume': sell_qty,
        })

    opportunities.sort(key=lambda x: x['expected_profit_per_gold'], reverse=True)
    return opportunities


def greedy_allocate(opportunities, budget_gold, max_items=50,
                     min_order_gold=0.01):
    """Greedy allocation: buy best items until budget exhausted."""
    budget_copper = budget_gold * 10000
    min_order_copper = min_order_gold * 10000
    allocations = {}

    for opp in opportunities:
        if len(allocations) >= max_items:
            break

        max_afford = budget_copper // opp['buy_price']
        qty = min(max_afford, opp['max_qty'])

        if qty <= 0:
            continue
        if qty * opp['buy_price'] < min_order_copper:
            continue

        cost = qty * opp['buy_price']
        budget_copper -= cost
        allocations[opp['item_id']] = qty

    return allocations


def lp_allocate(opportunities, budget_gold):
    """Linear program via scipy. No cardinality constraint."""
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
    """Main entry point."""
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
