"""
item_catalogue.py

Analyzes the aggregated buy/sell history from gw2efficiency exports
to extract useful trading insights.
"""

import pandas as pd

def analyze_trading_portfolio(buy_csv, sell_csv):
    """
    Analyze gw2efficiency export data to find:
    - Most traded items
    - Profit margins
    - Items to focus on for modeling
    """
    
    # Read CSVs with error handling for malformed lines
    buys = pd.read_csv(buy_csv, on_bad_lines='skip')
    sells = pd.read_csv(sell_csv, on_bad_lines='skip')
    
    # Rename for consistency
    buys = buys.rename(columns={
        'Item ID': 'item_id',
        'Item Name': 'item_name',
        'Item Amount': 'quantity_bought',
        'Your Buy Price': 'avg_buy_price'
    })
    
    sells = sells.rename(columns={
        'Item ID': 'item_id',
        'Item Name': 'item_name',
        'Item Amount': 'quantity_sold',
        'Your Sell Price': 'avg_sell_price'
    })
    
    # Aggregate by item (some items have multiple rows)
    buys_agg = buys.groupby(['item_id', 'item_name']).agg({
        'quantity_bought': 'sum',
        'avg_buy_price': 'mean'
    }).reset_index()
    
    sells_agg = sells.groupby(['item_id', 'item_name']).agg({
        'quantity_sold': 'sum',
        'avg_sell_price': 'mean'
    }).reset_index()
    
    # Merge buys and sells
    portfolio = pd.merge(
        buys_agg, 
        sells_agg, 
        on=['item_id', 'item_name'], 
        how='outer',
        suffixes=('_buy', '_sell')
    )
    
    # Fill NaNs (items only bought or only sold)
    portfolio['quantity_bought'] = portfolio['quantity_bought'].fillna(0)
    portfolio['quantity_sold'] = portfolio['quantity_sold'].fillna(0)
    
    # Calculate metrics
    portfolio['total_volume'] = portfolio['quantity_bought'] + portfolio['quantity_sold']
    portfolio['profit_per_item'] = portfolio['avg_sell_price'] - portfolio['avg_buy_price']
    portfolio['profit_margin_pct'] = (portfolio['profit_per_item'] / portfolio['avg_buy_price']) * 100
    portfolio['estimated_total_profit'] = portfolio['profit_per_item'] * portfolio['quantity_sold']
    
    # Sort by total volume (most traded items)
    portfolio = portfolio.sort_values('total_volume', ascending=False)
    
    return portfolio


def print_top_items(portfolio, n=20):
    """Print the top N most traded items"""
    print("="*80)
    print(f"TOP {n} MOST TRADED ITEMS (Last 90 Days)")
    print("="*80)
    
    top = portfolio.head(n)
    
    for idx, row in top.iterrows():
        print(f"\n{row['item_name']}")
        print(f"  ID: {int(row['item_id'])}")
        print(f"  Volume: {int(row['quantity_bought'])} bought, {int(row['quantity_sold'])} sold")
        
        if pd.notna(row['avg_buy_price']) and pd.notna(row['avg_sell_price']):
            print(f"  Prices: {int(row['avg_buy_price'])}c buy → {int(row['avg_sell_price'])}c sell")
            print(f"  Margin: {int(row['profit_per_item'])}c ({row['profit_margin_pct']:.1f}%)")
            print(f"  Est. Profit: {int(row['estimated_total_profit'])}c = {int(row['estimated_total_profit']/10000)}g")


def export_item_list(portfolio, filepath='data/my_trading_items.csv'):
    """Export just the item IDs and names for use in optimizer"""
    items = portfolio[['item_id', 'item_name', 'total_volume']].copy()
    items = items[items['total_volume'] > 0]  # Only items actually traded
    items.to_csv(filepath, index=False)
    print(f"\nExported {len(items)} traded items to {filepath}")


def main():
    buy_csv = 'data/gw2efficiency_buy_history.csv'
    sell_csv = 'data/gw2efficiency_sell_history.csv'
    
    print("Analyzing gw2efficiency export data...")
    portfolio = analyze_trading_portfolio(buy_csv, sell_csv)
    
    print_top_items(portfolio, n=20)
    
    print("\n" + "="*80)
    print("SUMMARY STATISTICS")
    print("="*80)
    print(f"Unique items traded: {len(portfolio)}")
    print(f"Total buy volume: {int(portfolio['quantity_bought'].sum())}")
    print(f"Total sell volume: {int(portfolio['quantity_sold'].sum())}")
    
    if portfolio['estimated_total_profit'].notna().any():
        total_profit = portfolio['estimated_total_profit'].sum()
        print(f"Estimated total profit: {int(total_profit)}c = {int(total_profit/10000)}g")
    
    # Export item list
    export_item_list(portfolio)
    
    # Save full analysis
    portfolio.to_csv('data/trading_portfolio_analysis.csv', index=False)
    print("\nFull analysis saved to data/trading_portfolio_analysis.csv")


if __name__ == '__main__':
    main()