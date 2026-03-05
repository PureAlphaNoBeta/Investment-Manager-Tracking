import sqlite3
import pandas as pd
import os

DB_PATH = os.path.join("data", "hedge_funds.db")
LIST_PATH = "missing_cusips_list.csv"
UPLOAD_PATH = "bloomberg_upload.csv"

def export_missing_template():
    if not os.path.exists(DB_PATH):
        print("❌ Database not found.")
        return

    conn = sqlite3.connect(DB_PATH)
    
    # 1. Get unique CUSIPs and their active date ranges
    query = """
        SELECT cusip, MAX(name_of_issuer) as name_of_issuer, 
               MIN(report_date) as first_held, MAX(report_date) as last_held
        FROM holdings
        WHERE put_call IS NULL
        AND shares > 0
        AND (
            ticker = 'UNKNOWN' 
            OR ticker IS NULL 
            OR ticker LIKE 'SYN_%'
            OR ticker NOT IN (SELECT DISTINCT ticker FROM stock_prices)
        )
        GROUP BY cusip
        ORDER BY name_of_issuer
    """
    df_missing = pd.read_sql(query, conn)
    conn.close()

    if df_missing.empty:
        print("✨ No missing or synthetic assets found! Your database is fully priced.")
        return

    # Export the clean list for your reference when using the Bloomberg Terminal
    df_missing.to_csv(LIST_PATH, index=False)
    
    # Create an empty template for uploading Bloomberg data back into the system
    if not os.path.exists(UPLOAD_PATH):
        pd.DataFrame(columns=['Date', 'cusip', 'price']).to_csv(UPLOAD_PATH, index=False)
    
    print(f"✅ Exported {len(df_missing)} unique CUSIPs to '{LIST_PATH}' for your Bloomberg queries.")
    print(f"👉 When you pull the time-series data, format it in '{UPLOAD_PATH}' (Date, cusip, price) and run Step 2.")

def import_and_process_prices():
    if not os.path.exists(DB_PATH):
        print("❌ Database not found.")
        return
        
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    bbg_cusips = set()
    bbg_count = 0
    
    # 1. Ingest the entire Bloomberg Time Series directly
    if os.path.exists(UPLOAD_PATH):
        try:
            df_bbg = pd.read_csv(UPLOAD_PATH).dropna()
            if not df_bbg.empty:
                # Format to match our database
                df_bbg['ticker'] = "BBG_" + df_bbg['cusip'].astype(str)
                df_bbg['Date'] = pd.to_datetime(df_bbg['Date']).dt.strftime('%Y-%m-%d')
                
                # Keep track of which CUSIPs we successfully got BBG data for
                bbg_cusips = set(df_bbg['cusip'].astype(str).tolist())
                
                # Drop the original cusip column and push the raw time series to the database
                df_bbg_prices = df_bbg[['Date', 'ticker', 'price']].drop_duplicates()
                df_bbg_prices.to_sql('stock_prices', conn, if_exists='append', index=False)
                bbg_count = len(df_bbg_prices)
                print(f"📈 Ingested {bbg_count} monthly price points from Bloomberg!")
        except Exception as e:
            print(f"⚠️ Could not read {UPLOAD_PATH} properly. Error: {e}")

    # 2. Process Holdings: Assign BBG_ where we have data, generate SYN_ where we don't
    query_holdings = """
        SELECT report_date, cusip, standardized_market_value, shares
        FROM holdings
        WHERE put_call IS NULL
        AND shares > 0
        AND (
            ticker = 'UNKNOWN' 
            OR ticker IS NULL 
            OR ticker LIKE 'SYN_%'
            OR ticker NOT IN (SELECT DISTINCT ticker FROM stock_prices)
        )
    """
    df_holdings = pd.read_sql(query_holdings, conn)
    
    syn_prices_to_insert = []
    syn_count = 0
    
    print("🔄 Mapping Holdings to BBG or calculating Synthetic Prices...")
    
    for _, row in df_holdings.iterrows():
        cusip = str(row['cusip'])
        date = str(row['report_date'])
        
        # If this CUSIP has Bloomberg data in our upload, map the holding to BBG_
        if cusip in bbg_cusips:
            final_ticker = "BBG_" + cusip
        else:
            # Fallback to Implied Synthetic Price (Value / Shares)
            final_ticker = "SYN_" + cusip
            final_price = round(float(row['standardized_market_value']) / float(row['shares']), 4)
            syn_prices_to_insert.append((date, final_ticker, final_price))
            syn_count += 1
            
        # Update the holdings table so it knows which ticker to look for
        cursor.execute("""
            UPDATE holdings 
            SET ticker = ? 
            WHERE cusip = ? AND report_date = ?
        """, (final_ticker, cusip, date))

    # 3. Save any generated Synthetic Prices
    if syn_prices_to_insert:
        df_syn_prices = pd.DataFrame(syn_prices_to_insert, columns=['Date', 'ticker', 'price'])
        df_syn_prices = df_syn_prices.drop_duplicates(subset=['Date', 'ticker'])
        df_syn_prices.to_sql('stock_prices', conn, if_exists='append', index=False)

    # 4. Cleanup any accidental exact duplicates in the database
    conn.execute("""
        DELETE FROM stock_prices 
        WHERE rowid NOT IN (
            SELECT MIN(rowid) FROM stock_prices GROUP BY Date, ticker
        )
    """)
    
    conn.commit()
    conn.close()
    
    print(f"✅ Database Update Complete!")
    print(f"  -> {len(bbg_cusips)} Assets mapped to Premium Bloomberg Data.")
    print(f"  -> {syn_count} Quarters mapped to Implied Synthetic Pricing.")

if __name__ == "__main__":
    print("=========================================")
    print("   🏢 HYBRID PRICING ENGINE (BBG/SYN)    ")
    print("=========================================")
    print("1. Export Missing CUSIPs List")
    print("2. Import Bloomberg CSV and Update Database")
    
    choice = input("\nEnter 1 or 2: ").strip()
    
    if choice == '1':
        export_missing_template()
    elif choice == '2':
        import_and_process_prices()
    else:
        print("Invalid choice. Exiting.")