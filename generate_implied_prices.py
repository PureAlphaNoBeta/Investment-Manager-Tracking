import sqlite3
import pandas as pd
import os

def generate_synthetic_prices():
    db_path = os.path.join("data", "hedge_funds.db")
    if not os.path.exists(db_path):
        print("❌ Database not found.")
        return

    conn = sqlite3.connect(db_path)
    
    print("🔍 Scanning for missing assets (UNKNOWNs & unpriced SPACs) to generate Implied Prices...")

    # 1. Pull all holdings that need synthetic prices
    # This catches OpenFIGI failures AND Yahoo Finance failures
    query = """
        SELECT report_date, cusip, name_of_issuer, ticker as original_ticker, standardized_market_value, shares
        FROM holdings
        WHERE put_call IS NULL
        AND shares > 0
        AND (
            ticker = 'UNKNOWN' 
            OR ticker IS NULL 
            OR ticker NOT IN (SELECT DISTINCT ticker FROM stock_prices)
        )
    """
    df_missing = pd.read_sql(query, conn)

    if df_missing.empty:
        print("✨ No missing stocks found to synthesize. You are at 100%!")
        conn.close()
        return

    # 2. Calculate the Implied Price (Value / Shares)
    df_missing['price'] = df_missing['standardized_market_value'] / df_missing['shares']
    
    # 3. Create a Synthetic Ticker
    # We use the CUSIP to ensure it is perfectly unique and avoids weird SPAC slash characters
    df_missing['ticker'] = 'SYN_' + df_missing['cusip']
    
    # 4. Format for the stock_prices table
    df_prices = df_missing[['report_date', 'ticker', 'price']].rename(columns={'report_date': 'Date'})
    
    # Drop duplicates (if multiple funds held the exact same asset on the exact same date)
    df_prices = df_prices.drop_duplicates(subset=['Date', 'ticker'])

    # 5. Inject Prices into Database
    df_prices.to_sql('stock_prices', conn, if_exists='append', index=False)
    
    # 6. Update the holdings table so the dashboard knows to look for the SYN_ ticker
    print(f"  -> Updating holdings table with synthetic tickers...")
    cursor = conn.cursor()
    
    # Get unique CUSIPs and their new Synthetic Tickers to update the database
    unique_updates = df_missing[['cusip', 'ticker']].drop_duplicates()
    
    for _, row in unique_updates.iterrows():
        # Update the holding row to use the SYN_ ticker so it links properly to our new prices
        cursor.execute("""
            UPDATE holdings 
            SET ticker = ? 
            WHERE cusip = ? 
            AND (ticker = 'UNKNOWN' OR ticker IS NULL OR ticker NOT IN (SELECT DISTINCT ticker FROM stock_prices))
        """, (row['ticker'], row['cusip']))
        
    conn.commit()
    conn.close()
    
    print(f"✅ Successfully generated {len(df_prices)} synthetic price points for {len(unique_updates)} unpriced assets!")

if __name__ == "__main__":
    generate_synthetic_prices()