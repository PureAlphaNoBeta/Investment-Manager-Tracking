import sqlite3
import pandas as pd
import os

def fix_existing_database_dates():
    db_path = os.path.join("data", "hedge_funds.db")
    if not os.path.exists(db_path):
        print("❌ Database not found at:", db_path)
        return

    conn = sqlite3.connect(db_path)
    
    # --- 1. Fix Stock Prices ---
    print("🛠️ Shifting dates in 'stock_prices' to end-of-month...")
    try:
        df_prices = pd.read_sql("SELECT * FROM stock_prices", conn)
        if not df_prices.empty:
            # Shift to the last day of the month
            df_prices['Date'] = pd.to_datetime(df_prices['Date']) + pd.offsets.MonthEnd(0)
            df_prices['Date'] = df_prices['Date'].dt.strftime('%Y-%m-%d')
            
            # Drop any duplicates just in case the shift caused overlapping dates
            df_prices = df_prices.drop_duplicates(subset=['Date', 'ticker'])
            
            # Overwrite the table
            df_prices.to_sql('stock_prices', conn, if_exists='replace', index=False)
            print(f"✅ Successfully aligned {len(df_prices)} historical stock prices.")
    except Exception as e:
        print(f"❌ Error processing stock_prices: {e}")

    # --- 2. Fix Benchmarks ---
    print("\n🛠️ Shifting dates in 'benchmarks' to end-of-month...")
    try:
        df_bench = pd.read_sql("SELECT * FROM benchmarks", conn)
        if not df_bench.empty:
            df_bench['Date'] = pd.to_datetime(df_bench['Date']) + pd.offsets.MonthEnd(0)
            df_bench['Date'] = df_bench['Date'].dt.strftime('%Y-%m-%d')
            
            df_bench = df_bench.drop_duplicates(subset=['Date'])
            
            df_bench.to_sql('benchmarks', conn, if_exists='replace', index=False)
            print(f"✅ Successfully aligned {len(df_bench)} benchmark records.")
    except Exception as e:
        print(f"❌ Error processing benchmarks: {e}")

    conn.close()
    print("\n🎉 Database alignment complete! Your dashboard dates are now perfectly synced to 13F quarters.")

if __name__ == "__main__":
    fix_existing_database_dates()