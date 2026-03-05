import sqlite3
import pandas as pd
import os
import sys
from datetime import datetime

# Allow Python to find our other files in the project directory
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from edgar_scraper import get_historical_13f_urls, parse_and_standardize_13f
from utils.ticker_mapping import map_cusips_to_tickers

# --- Import the Financial Data Engines ---
from utils.performance_math import download_historical_prices, download_company_info, download_benchmarks

def aggregate_13f_holdings(df_raw):
    """
    Consolidates multiple rows of the same asset into a single unified position.
    Strictly separates Equities, Puts, and Calls.
    """
    print("  -> Standardizing corporate names and aggregating rows...")
    
    # --- NEW NAME STANDARDIZATION LOGIC ---
    # 1. Sort by date to ensure the newest filing is at the bottom
    df_raw = df_raw.sort_values('report_date')
    
    # 2. Create a mapping of CUSIP -> Most Recent Name
    latest_names = df_raw.groupby('cusip')['name_of_issuer'].last()
    
    # 3. Overwrite all historical names with the newest name
    df_raw['name_of_issuer'] = df_raw['cusip'].map(latest_names)
    # --------------------------------------
    
    aggregation_rules = {
        'name_of_issuer': 'first',
        'title_of_class': 'first',
        'standardized_market_value': 'sum', 
        'shares': 'sum'                     
    }

    df_agg = df_raw.groupby(
        ['fund_name', 'report_date', 'cusip', 'put_call'], 
        dropna=False
    ).agg(aggregation_rules).reset_index()
    
    total_portfolio_value = df_agg.groupby(['fund_name', 'report_date'])['standardized_market_value'].transform('sum')
    df_agg['portfolio_weight_pct'] = (df_agg['standardized_market_value'] / total_portfolio_value) * 100
    
    return df_agg


def run_etl_pipeline(update_13f=False):
    print(f"[{datetime.now()}] Starting Historical Hedge Fund ETL Pipeline...")
    
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    data_dir = os.path.join(base_dir, 'data')
    excel_path = os.path.join(data_dir, 'funds_list.xlsx')
    db_path = os.path.join(data_dir, 'hedge_funds.db')
    
    os.makedirs(data_dir, exist_ok=True)
    
    # ==========================================
    # 1. EXTRACT, TRANSFORM, AND TRANSLATE (SEC & OpenFIGI)
    # ==========================================
    if update_13f:
        if not os.path.exists(excel_path):
            print(f"\nERROR: Could not find your Excel file at: {excel_path}")
            return
            
        print(f"Reading fund list from {excel_path}...")
        try:
            df_funds_metadata = pd.read_excel(excel_path)
        except Exception as e:
            print(f"Failed to read Excel file. Error: {e}")
            return
        
        df_funds_metadata['cik'] = df_funds_metadata['cik'].astype(str).apply(lambda x: x.split('.')[0].zfill(10))
        
        all_holdings = []
        
        for index, row in df_funds_metadata.iterrows():
            name = row['fund_name']
            cik = row['cik']
            print(f"\nProcessing {name} (CIK: {cik})...")
            
            historical_filings = get_historical_13f_urls(cik, years_back=10)
            
            if not historical_filings:
                print(f"  -> FAILED: Could not locate any 13Fs for {name}.")
                continue
                
            fund_position_count = 0
            for xml_url, report_date in historical_filings:
                print(f"    -> Scraping quarter ending {report_date}...")
                df_quarter_holdings = parse_and_standardize_13f(xml_url, name, report_date)
                
                if df_quarter_holdings is not None and not df_quarter_holdings.empty:
                    all_holdings.append(df_quarter_holdings)
                    fund_position_count += len(df_quarter_holdings)
                    
            print(f"  -> Success: Extracted a total of {fund_position_count} historical positions for {name}.")
                
        if not all_holdings:
            print("\nNo data extracted across any funds. Exiting pipeline.")
            return
            
        df_raw_master = pd.concat(all_holdings, ignore_index=True)
        print(f"\n--- DATA TRANSFORMATION ---")
        print(f"Total raw rows extracted across all funds: {len(df_raw_master)}")
        
        df_master = aggregate_13f_holdings(df_raw_master)
        print(f"Total consolidated positions after aggregation: {len(df_master)}")
        
        # !!! DONT FORGET TO PUT YOUR OPENFIGI API KEY HERE !!!
        df_master = map_cusips_to_tickers(df_master, api_key="67698733-810d-4c7a-bf5f-db85c841fb41")
        
        print(f"\n--- SAVING TO DATABASE ---")
        print(f"Connecting to database at: {db_path}")
        conn = sqlite3.connect(db_path)
        
        try:
            df_funds_metadata.to_sql('funds', conn, if_exists='replace', index=False)
            print("  -> 'funds' table successfully updated.")
            
            df_master.to_sql('holdings', conn, if_exists='replace', index=False)
            print("  -> 'holdings' table successfully updated.")
            
        except Exception as e:
            print(f"Database Error: {e}")
        finally:
            conn.close()
            
    else:
        print("\n[SKIPPING 13F & OPENFIGI] - 'update_13f' is set to False.")
        print("Jumping straight to updating Yahoo Finance prices...")

    # ==========================================
    # 2. LOAD FINANCIAL DATA (Yahoo Finance)
    # ==========================================
    download_historical_prices(db_path)
    download_company_info(db_path)
    download_benchmarks(db_path) 
    




    print(f"\n[{datetime.now()}] ETL Pipeline Complete! Your database is ready.")

if __name__ == "__main__":
    # --- MASTER TOGGLE SWITCH ---
    # Change to True when you add new funds to Excel.
    # Change to False if you just want to update Yahoo Finance prices.
    run_etl_pipeline(update_13f=False)