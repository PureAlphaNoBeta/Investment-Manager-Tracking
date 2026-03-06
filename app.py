import streamlit as st
import pandas as pd
import sqlite3
import os
import numpy as np

# 🚀 1. Import your modularized tabs
from tabs import tab1_universe_overview, tab2_manager_performance, tab3_manager_overview, tab4_stock_crowding, tab5_fund_map

# --- PAGE SETUP ---
st.set_page_config(page_title="13F Master Dashboard", layout="wide", initial_sidebar_state="expanded")
st.title("📈 Hedge Fund Tracker")

FUND_STRATEGIES = {
    "Pershing Square": "Activist", 
    "Lone Pine": "L/S Equity",
    "Coatue Management": "Technology L/S",
}

# --- 1. DATA INGESTION ENGINE ---
@st.cache_data
def load_database_data():
    db_path = os.path.join("data", "hedge_funds.db")
    if not os.path.exists(db_path):
        return None, None, None, None
    conn = sqlite3.connect(db_path)
    
    query = "SELECT h.*, c.sector, c.industry FROM holdings h LEFT JOIN company_info c ON h.ticker = c.ticker"
    df = pd.read_sql(query, conn)
    df_prices = pd.read_sql("SELECT * FROM stock_prices", conn)
    
    try: 
        df_benchmarks = pd.read_sql("SELECT * FROM benchmarks", conn)
    except: 
        df_benchmarks = pd.DataFrame()
    
    try:
        df_funds = pd.read_sql("SELECT * FROM funds", conn)
    except:
        df_funds = pd.DataFrame()
        
    conn.close()
    
    df['report_date'] = pd.to_datetime(df['report_date'])
    df['put_call'] = df['put_call'].fillna('SHARE')
    df['Strategy'] = df['fund_name'].apply(lambda x: FUND_STRATEGIES.get(x, "Generalist"))
    df['sector'] = df['sector'].fillna('').replace('Unknown', '')
    is_acq = df['name_of_issuer'].str.contains('ACQUISITION|ACQUISTN|SPAC|ACQ', case=False, na=False)
    is_empty_sector = (df['sector'] == '')
    df.loc[is_empty_sector & is_acq, 'sector'] = 'ACQ Corps / SPACs'
    df['sector'] = df['sector'].replace('', 'Unknown')
    
    df['pricing_fidelity'] = np.where(df['ticker'].str.startswith('BBG_'), 'Bloomberg (Premium)', 
                             np.where(df['ticker'].str.startswith('SYN_'), 'Implied (Synthetic)', 'Standard (Yahoo)'))
    
    df_prices['Date'] = pd.to_datetime(df_prices['Date'])
    if not df_benchmarks.empty: 
        df_benchmarks['Date'] = pd.to_datetime(df_benchmarks['Date'])
        
    return df, df_prices, df_benchmarks, df_funds

# --- 2. PERFORMANCE CALCULATION ENGINE (WITH LIVE PROJECTION) ---
@st.cache_data
def calculate_performance_metrics(df_valid, df_prices):
    quarters = sorted(df_valid['report_date'].unique())
    cum_data, contrib_data, s_data = [], [], []
    
    # Find the absolute latest market date we pulled from Yahoo Finance
    latest_price_date = df_prices['Date'].max()
    
    for fund in df_valid['fund_name'].unique():
        f_df = df_valid[df_valid['fund_name'] == fund]
        cum_ret, a_cum, s_cum = 1.0, 1.0, 1.0 
        
        # --- 1. HISTORICAL QUARTERS LOOP ---
        for i in range(len(quarters) - 1):
            cq, nq = quarters[i], quarters[i+1]
            pq = f_df[f_df['report_date'] == cq]
            if pq.empty: continue
                
            tkrs = pq['ticker'].tolist()
            
            p_start = df_prices[(df_prices['Date'] >= cq) & (df_prices['ticker'].isin(tkrs))].groupby('ticker').first().reset_index()
            p_end = df_prices[(df_prices['Date'] >= nq) & (df_prices['ticker'].isin(tkrs))].groupby('ticker').first().reset_index()
            
            if p_start.empty or p_end.empty: continue

            rets = pd.merge(p_start[['ticker', 'price']], p_end[['ticker', 'price']], on='ticker', suffixes=('_s', '_e'))
            rets['ret'] = (rets['price_e'] - rets['price_s']) / rets['price_s']
            p_rets = pd.merge(pq[['ticker', 'adjusted_weight', 'name_of_issuer']], rets, on='ticker')
            
            p_rets['contrib'] = p_rets['adjusted_weight'] * p_rets['ret']
            for _, r in p_rets.iterrows(): 
                contrib_data.append({'Fund': fund, 'Ticker': r['ticker'], 'Company': r['name_of_issuer'], 'Contrib': r['contrib']})
            
            q_ret = p_rets['contrib'].sum()
            cum_ret *= (1 + q_ret)
            cum_data.append({'Fund': fund, 'Date': nq, 'Cum_Ret': cum_ret, 'Q_Ret': q_ret})

            # Shadow Trader Math (60-day lag)
            a_cum *= (1 + q_ret)
            sq_s, sq_e = cq + pd.DateOffset(months=2), nq + pd.DateOffset(months=2)
            ps_s = df_prices[(df_prices['Date'] >= sq_s) & (df_prices['ticker'].isin(tkrs))].groupby('ticker').first().reset_index()
            ps_e = df_prices[(df_prices['Date'] >= sq_e) & (df_prices['ticker'].isin(tkrs))].groupby('ticker').first().reset_index()
            
            if not ps_s.empty and not ps_e.empty:
                rs = pd.merge(ps_s[['ticker', 'price']], ps_e[['ticker', 'price']], on='ticker', suffixes=('_s','_e'))
                ms = pd.merge(pq[['ticker', 'adjusted_weight']], rs, on='ticker')
                s_cum *= (1 + (ms['adjusted_weight'] * ((ms['price_e']-ms['price_s'])/ms['price_s'])).sum())
            
            s_data.append({'Fund': fund, 'Date': nq, 'Actual %': (a_cum-1)*100, 'Shadow %': (s_cum-1)*100})
            
        # --- 2. LIVE PROJECTION (HOLDING TO PRESENT DAY) ---
        if len(quarters) > 0 and latest_price_date > quarters[-1]:
            last_q = quarters[-1]
            pq = f_df[f_df['report_date'] == last_q] # The final 13F filing
            
            if not pq.empty:
                tkrs = pq['ticker'].tolist()
                p_start = df_prices[(df_prices['Date'] >= last_q) & (df_prices['ticker'].isin(tkrs))].groupby('ticker').first().reset_index()
                
                # Fetch the present day price
                p_end = df_prices[(df_prices['Date'] == latest_price_date) & (df_prices['ticker'].isin(tkrs))].groupby('ticker').first().reset_index()
                
                if not p_start.empty and not p_end.empty:
                    rets = pd.merge(p_start[['ticker', 'price']], p_end[['ticker', 'price']], on='ticker', suffixes=('_s', '_e'))
                    rets['ret'] = (rets['price_e'] - rets['price_s']) / rets['price_s']
                    p_rets = pd.merge(pq[['ticker', 'adjusted_weight', 'name_of_issuer']], rets, on='ticker')
                    
                    p_rets['contrib'] = p_rets['adjusted_weight'] * p_rets['ret']
                    for _, r in p_rets.iterrows(): 
                        contrib_data.append({'Fund': fund, 'Ticker': r['ticker'], 'Company': r['name_of_issuer'], 'Contrib': r['contrib']})
                    
                    q_ret = p_rets['contrib'].sum()
                    cum_ret *= (1 + q_ret)
                    
                    # Append the live data point to the charts!
                    cum_data.append({'Fund': fund, 'Date': latest_price_date, 'Cum_Ret': cum_ret, 'Q_Ret': q_ret})
                    
                    # Shadow Trader live projection
                    a_cum *= (1 + q_ret)
                    sq_s = last_q + pd.DateOffset(months=2) # Shadow enters 60 days after Q4 ends
                    
                    if latest_price_date > sq_s:
                        ps_s = df_prices[(df_prices['Date'] >= sq_s) & (df_prices['ticker'].isin(tkrs))].groupby('ticker').first().reset_index()
                        ps_e = df_prices[(df_prices['Date'] == latest_price_date) & (df_prices['ticker'].isin(tkrs))].groupby('ticker').first().reset_index()
                        
                        if not ps_s.empty and not ps_e.empty:
                            rs = pd.merge(ps_s[['ticker', 'price']], ps_e[['ticker', 'price']], on='ticker', suffixes=('_s','_e'))
                            ms = pd.merge(pq[['ticker', 'adjusted_weight']], rs, on='ticker')
                            s_cum *= (1 + (ms['adjusted_weight'] * ((ms['price_e']-ms['price_s'])/ms['price_s'])).sum())
                    
                    s_data.append({'Fund': fund, 'Date': latest_price_date, 'Actual %': (a_cum-1)*100, 'Shadow %': (s_cum-1)*100})
            
    return pd.DataFrame(cum_data), pd.DataFrame(contrib_data), pd.DataFrame(s_data)

# --- 3. DATA PREPARATION (CACHED FOR SPEED) ---
@st.cache_data
def prepare_analysis_data(df_raw, df_prices):
    # Create a general-purpose dataframe for SHARES only
    df_filtered_shares = df_raw[df_raw['put_call'] == 'SHARE'].copy()
    
    # Create a dataframe that includes ALL position types
    df_filtered_all_types = df_raw.copy()
    
    # AUM Calculation
    def add_aum_concentration(df):
        if not df.empty:
            total_aum = df.groupby(['report_date', 'fund_name'])['standardized_market_value'].sum().reset_index(name='Total AUM')
            df = pd.merge(df, total_aum, on=['report_date', 'fund_name'])
            df['Concentration %'] = (df['standardized_market_value'] / df['Total AUM']) * 100
        return df

    df_filtered_shares = add_aum_concentration(df_filtered_shares)
    df_filtered_all_types = add_aum_concentration(df_filtered_all_types)
    
    # Prepare Validation DF for Performance
    df_equities = df_filtered_shares.copy()
    valid_tkrs = set(df_prices['ticker'].unique())
    df_equities['has_price'] = df_equities['ticker'].isin(valid_tkrs)
    df_valid = df_equities[df_equities['has_price']].copy()
    
    if not df_valid.empty:
        q_v_aum = df_valid.groupby(['report_date', 'fund_name'])['standardized_market_value'].sum().reset_index(name='V_AUM')
        df_valid = pd.merge(df_valid, q_v_aum, on=['report_date', 'fund_name'])
        df_valid['adjusted_weight'] = df_valid.apply(lambda row: row['standardized_market_value'] / row['V_AUM'] if row['V_AUM'] > 0 else 0, axis=1)
        
    return df_filtered_shares, df_filtered_all_types, df_valid, df_equities

# --- INIT DATA ---
df_raw, df_prices, df_bench, df_funds = load_database_data()
if df_raw is None or df_raw.empty:
    st.error("⚠️ Database empty! Please run your ETL pipeline.")
    st.stop()

ticker_to_name = dict(zip(df_raw['ticker'], df_raw['name_of_issuer']))

# --- 4. MASTER FILTERS & DATA PREP ---
st.sidebar.header("About")
st.sidebar.info("This dashboard provides an analysis of hedge fund 13F filings, focusing on long-term trends and manager strategies.")

# Filters are now applied programmatically, not via user input in the sidebar
all_funds = sorted(df_raw['fund_name'].unique())
selected_funds = all_funds  # Select all funds by default
chart_template = "plotly_dark"

# Run the cached data preparation
df_filtered_shares, df_filtered_all_types, df_valid, df_equities = prepare_analysis_data(df_raw, df_prices)

if not df_valid.empty:
    df_cum, df_contrib, df_shadow = calculate_performance_metrics(df_valid, df_prices)

    t1, t2, t3, t4, t5 = st.tabs([
        "Universe Overview",
        "Manager Performance",
        "Manager Portfolio",
        "Stock Crowding",
        "Manager & Peer Location"
    ])

    # 🚀 2. Pass the correct dataframes down to the independent tab modules
    with t1:
        tab1_universe_overview.render(df_filtered_shares, df_raw, ticker_to_name, chart_template, df_valid, df_prices, df_bench)
    with t2:
        tab2_manager_performance.render(df_cum, df_shadow, df_contrib, df_bench, df_equities, selected_funds, chart_template, df_valid, df_prices)
    with t3:
        # Note: Passing the dataframe with all position types here
        tab3_manager_overview.render(df_filtered_all_types, df_raw, ticker_to_name, selected_funds, chart_template, df_funds)
    with t4:
        tab4_stock_crowding.render(df_filtered_all_types, df_prices, df_bench, ticker_to_name, chart_template)
    with t5:
        tab5_fund_map.render(df_raw, df_funds, selected_funds)
else:
    st.warning("No valid data with pricing history available. Performance and some analytics may be disabled.")
    # Still render the tabs that can function without performance data
    t1, t2, t3, t4, t5 = st.tabs([
        "Universe Overview",
        "Manager Performance",
        "Manager Overview",
        "Stock Crowding",
        "Geographic Map"
    ])
    with t1:
         tab1_universe_overview.render(df_filtered_shares, df_raw, ticker_to_name, chart_template, pd.DataFrame(), df_prices, df_bench)
    with t2:
        st.warning("Cannot calculate manager performance without pricing data.")
    with t3:
        tab3_manager_overview.render(df_filtered_all_types, df_raw, ticker_to_name, selected_funds, chart_template, df_funds)
    with t4:
        tab4_stock_crowding.render(df_filtered_all_types, df_prices, df_bench, ticker_to_name, chart_template)
    with t5:
        tab5_fund_map.render(df_raw, df_funds, selected_funds)