import sqlite3
import pandas as pd
import yfinance as yf

def download_historical_prices(db_path):
    print("\n--- DOWNLOADING FINANCIAL DATA (Yahoo Finance) ---")
    conn = sqlite3.connect(db_path)
    
    query = "SELECT DISTINCT ticker FROM holdings WHERE ticker != 'UNKNOWN'"
    try:
        df_tickers = pd.read_sql(query, conn)
    except Exception as e:
        print(f"  -> Could not read holdings table. Error: {e}")
        conn.close()
        return

    tickers = df_tickers['ticker'].tolist()
    if not tickers:
        print("  -> No valid tickers found to download.")
        conn.close()
        return
        
    print(f"  -> Found {len(tickers)} valid tickers. Fetching price history in batches of 200...")
    
    # Sanitize tickers for Yahoo
    yf_to_db = {t.replace('/', '-').replace('.', '-'): t for t in tickers}
    yf_tickers = list(yf_to_db.keys())
    
    # --- THE NEW BATCHING ENGINE ---
    chunk_size = 200
    all_prices_long = []
    
    for i in range(0, len(yf_tickers), chunk_size):
        chunk = yf_tickers[i:i + chunk_size]
        current_batch = (i // chunk_size) + 1
        total_batches = (len(yf_tickers) // chunk_size) + 1
        print(f"  -> Downloading batch {current_batch} of {total_batches}...")
        
        ticker_string = " ".join(chunk)
        data = yf.download(ticker_string, period="10y", interval="1mo", auto_adjust=True, progress=False)
        
        if data.empty:
            continue
            
        # Handle Yahoo's MultiIndex output vs Single output
        if isinstance(data.columns, pd.MultiIndex):
            if 'Close' in data:
                df_chunk = data['Close'].reset_index()
            else:
                continue
        else:
            df_chunk = data[['Close']].reset_index()
            df_chunk.rename(columns={'Close': chunk[0]}, inplace=True)
            
        # Melt and clean the chunk
        df_chunk_long = pd.melt(df_chunk, id_vars=['Date'], var_name='ticker', value_name='price')
        df_chunk_long = df_chunk_long.dropna()
        all_prices_long.append(df_chunk_long)
        
    if not all_prices_long:
        print("  -> Error: No prices downloaded across all batches.")
        conn.close()
        return
        
    # Combine all the chunks into one massive table
    df_prices_long = pd.concat(all_prices_long, ignore_index=True)
    
    # 🚀 THE FIX: Force Yahoo's 1st-of-month dates to the true End-of-Month!
    df_prices_long['Date'] = pd.to_datetime(df_prices_long['Date']) + pd.offsets.MonthEnd(0)
    df_prices_long['Date'] = df_prices_long['Date'].dt.strftime('%Y-%m-%d')
    
    # Map back to original database tickers and remove any accidental duplicates
    df_prices_long['ticker'] = df_prices_long['ticker'].map(yf_to_db).fillna(df_prices_long['ticker'])
    df_prices_long = df_prices_long.drop_duplicates(subset=['Date', 'ticker'])
    
    # Save to SQLite
    df_prices_long.to_sql('stock_prices', conn, if_exists='replace', index=False)
    print(f"  -> Success: Saved {len(df_prices_long)} total historical price records!")
    conn.close()

def download_company_info(db_path):
    print("\n--- DOWNLOADING COMPANY METADATA (Yahoo Finance) ---")
    conn = sqlite3.connect(db_path)
    
    query = "SELECT DISTINCT ticker FROM holdings WHERE ticker != 'UNKNOWN'"
    try:
        df_tickers = pd.read_sql(query, conn)
    except Exception:
        conn.close()
        return

    tickers = df_tickers['ticker'].tolist()
    if not tickers:
        conn.close()
        return
        
    print(f"  -> Fetching Sector, Industry, and Market Cap for {len(tickers)} companies...")
    
    metadata = []
    for tick in tickers:
        yf_tick = tick.replace('/', '-').replace('.', '-')
        try:
            stock = yf.Ticker(yf_tick)
            info = stock.info
            metadata.append({
                'ticker': tick,
                'sector': info.get('sector', 'Unknown'),
                'industry': info.get('industry', 'Unknown'),
                'market_cap': info.get('marketCap', 0),
                'beta': info.get('beta', 0.0)
            })
        except Exception:
            pass
            
    if metadata:
        df_meta = pd.DataFrame(metadata)
        df_meta.to_sql('company_info', conn, if_exists='replace', index=False)
        print(f"  -> Success: Saved metadata for {len(df_meta)} companies.")
    conn.close()

def download_benchmarks(db_path):
    """
    Downloads S&P 500 (SPY), MSCI World (URTH), and Risk-Free Rate (^IRX).
    """
    print("\n--- DOWNLOADING BENCHMARKS & RISK-FREE RATE ---")
    conn = sqlite3.connect(db_path)
    
    benchmark_tickers = ["SPY", "URTH", "^IRX"]
    print(f"  -> Fetching data for: {', '.join(benchmark_tickers)}")
    
    data = yf.download(" ".join(benchmark_tickers), period="10y", interval="1mo", auto_adjust=True, progress=False)
    
    if data.empty:
        print("  -> Warning: No benchmark data found.")
        conn.close()
        return
        
    if isinstance(data.columns, pd.MultiIndex):
        df_bench = data['Close'].reset_index()
    else:
        df_bench = data[['Close']].reset_index()
        
    # 🚀 THE FIX: Force Benchmark dates to End-of-Month!
    df_bench['Date'] = pd.to_datetime(df_bench['Date']) + pd.offsets.MonthEnd(0)
    df_bench['Date'] = df_bench['Date'].dt.strftime('%Y-%m-%d')
    
    df_bench.to_sql('benchmarks', conn, if_exists='replace', index=False)
    print(f"  -> Success: Saved benchmarks to database.")
    conn.close()