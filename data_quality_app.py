import streamlit as st
import sqlite3
import pandas as pd
import os
import plotly.express as px

# --- PAGE SETUP ---
st.set_page_config(page_title="Data Quality Control", layout="wide")
st.title("🩺 Data Quality & Coverage Control")
st.markdown("Use this dashboard to identify missing data, unpriced assets, and translation failures before analyzing fund performance.")

db_path = os.path.join("data", "hedge_funds.db")

@st.cache_data(ttl=60)
def load_quality_metrics():
    if not os.path.exists(db_path):
        return None
    
    conn = sqlite3.connect(db_path)
    
    # 1. Table Row Counts
    tables_list = ['funds', 'holdings', 'company_info', 'stock_prices', 'benchmarks']
    counts = {}
    for t in tables_list:
        try:
            counts[t] = pd.read_sql(f"SELECT COUNT(*) FROM {t}", conn).iloc[0,0]
        except:
            counts[t] = 0
            
    # 2. Translation & Pricing Metrics
    try:
        tot_cusips = pd.read_sql("SELECT COUNT(DISTINCT cusip) FROM holdings", conn).iloc[0,0]
        unk_cusips = pd.read_sql("SELECT COUNT(DISTINCT cusip) FROM holdings WHERE ticker = 'UNKNOWN'", conn).iloc[0,0]
        
        target_tickers = pd.read_sql("SELECT DISTINCT ticker FROM holdings WHERE ticker != 'UNKNOWN'", conn)['ticker'].tolist()
        priced_tickers = pd.read_sql("SELECT DISTINCT ticker FROM stock_prices", conn)['ticker'].tolist()
        
        missing_tickers = list(set(target_tickers) - set(priced_tickers))
    except Exception as e:
        tot_cusips, unk_cusips, target_tickers, priced_tickers, missing_tickers = 0, 0, [], [], []
        
    # 3. Impact Analysis (Missing Yahoo Prices) - SPLIT STOCKS, BONDS, AND OPTIONS
    try:
        query = """
            SELECT ticker, name_of_issuer, 
                   CASE 
                       WHEN put_call = 'Put' THEN 'Put'
                       WHEN put_call = 'Call' THEN 'Call'
                       WHEN title_of_class LIKE '%NOTE%' 
                         OR title_of_class LIKE '%BOND%' 
                         OR title_of_class LIKE '%CONV%' 
                         OR title_of_class LIKE '%PRN%' 
                         OR title_of_class LIKE '%DEB%' THEN 'Bond'
                       ELSE 'Stock'
                   END as asset_type, 
                   SUM(standardized_market_value) as total_historical_val 
            FROM holdings 
            WHERE ticker != 'UNKNOWN' 
            AND ticker NOT IN (SELECT DISTINCT ticker FROM stock_prices)
            GROUP BY ticker, name_of_issuer, asset_type
            ORDER BY total_historical_val DESC
        """
        df_impact = pd.read_sql(query, conn)
    except:
        df_impact = pd.DataFrame()
        
    # 4. Failed Translations (OpenFIGI UNKNOWNs) - SPLIT STOCKS, BONDS, AND OPTIONS
    try:
        query_unk = """
            SELECT cusip, name_of_issuer, 
                   CASE 
                       WHEN put_call = 'Put' THEN 'Put'
                       WHEN put_call = 'Call' THEN 'Call'
                       WHEN title_of_class LIKE '%NOTE%' 
                         OR title_of_class LIKE '%BOND%' 
                         OR title_of_class LIKE '%CONV%' 
                         OR title_of_class LIKE '%PRN%' 
                         OR title_of_class LIKE '%DEB%' THEN 'Bond'
                       ELSE 'Stock'
                   END as asset_type, 
                   SUM(standardized_market_value) as total_historical_val 
            FROM holdings 
            WHERE ticker = 'UNKNOWN'
            GROUP BY cusip, name_of_issuer, asset_type
            ORDER BY total_historical_val DESC
        """
        df_unknowns = pd.read_sql(query_unk, conn)
    except:
        df_unknowns = pd.DataFrame()

    conn.close()
    
    return counts, tot_cusips, unk_cusips, target_tickers, priced_tickers, missing_tickers, df_impact, df_unknowns

data = load_quality_metrics()

if not data:
    st.error("Database not found. Please run your ETL pipeline first.")
    st.stop()

counts, tot_cusips, unk_cusips, target_tickers, priced_tickers, missing_tickers, df_impact, df_unknowns = data

# --- METRICS ROW ---
st.subheader("1. Pipeline Health Check")
c1, c2, c3, c4 = st.columns(4)

translation_rate = ((tot_cusips - unk_cusips) / tot_cusips) * 100 if tot_cusips > 0 else 0
c1.metric("OpenFIGI Translation Rate", f"{translation_rate:.1f}%", help="Percentage of CUSIPs successfully mapped to a Ticker.")

price_coverage = (len(priced_tickers) / len(target_tickers)) * 100 if target_tickers else 0
c2.metric("Yahoo Finance Price Coverage", f"{price_coverage:.1f}%", help="Percentage of recognized tickers that actually have downloaded price data.")

c3.metric("Missing Prices (Count)", len(missing_tickers))
c4.metric("Total 13F Positions", f"{counts.get('holdings', 0):,}")

# --- IMPACT ANALYSIS ROW ---
st.markdown("---")
st.subheader("2. The 'Hit List' (Data Gaps by Historical $ Impact)")
st.write("These assets are missing from your database. The larger the dollar value, the more it will skew your final dashboard's performance math.")

tab1, tab2 = st.tabs(["Missing Prices (Yahoo Failed)", "Translation Failures (OpenFIGI Failed)"])

with tab1:
    if not df_impact.empty:
        col_pie, col_chart = st.columns([1, 2])
        
        with col_pie:
            type_breakdown = df_impact.groupby('asset_type')['total_historical_val'].sum().reset_index()
            fig_pie = px.pie(type_breakdown, values='total_historical_val', names='asset_type', 
                             hole=0.4, title="Missing Value by Type", template="plotly_dark")
            # Updated to new 2026 syntax
            st.plotly_chart(fig_pie, width='stretch')

        with col_chart:
            top_15_impact = df_impact.head(15).copy()
            fig = px.bar(top_15_impact, x='total_historical_val', y='ticker', color='asset_type', orientation='h', 
                         title="Top 15 Missing Tickers by $ Impact", text='name_of_issuer',
                         labels={'total_historical_val': 'Total Historical Value ($)', 'ticker': 'Ticker'},
                         template="plotly_dark")
            fig.update_layout(yaxis={'categoryorder':'total ascending'})
            # Updated to new 2026 syntax
            st.plotly_chart(fig, width='stretch')
            
        # Updated to new 2026 syntax
        st.dataframe(df_impact.style.format({'total_historical_val': '${:,.0f}'}), width='stretch', height=300)
    else:
        st.success("🎉 No missing prices! Yahoo Finance successfully downloaded everything.")

with tab2:
    if not df_unknowns.empty:
        col_pie_unk, col_chart_unk = st.columns([1, 2])
        
        with col_pie_unk:
            unk_breakdown = df_unknowns.groupby('asset_type')['total_historical_val'].sum().reset_index()
            fig_pie_unk = px.pie(unk_breakdown, values='total_historical_val', names='asset_type', 
                                 hole=0.4, title="Failed Value by Type", template="plotly_dark")
            # Updated to new 2026 syntax
            st.plotly_chart(fig_pie_unk, width='stretch')
            
        with col_chart_unk:
            top_15_unk = df_unknowns.head(15).copy()
            # Truncate long names for cleaner charts
            top_15_unk['short_name'] = top_15_unk['name_of_issuer'].str.slice(0, 20)
            fig_unk = px.bar(top_15_unk, x='total_historical_val', y='short_name', color='asset_type', orientation='h', 
                             title="Top 15 Translation Failures by $ Impact",
                             labels={'total_historical_val': 'Total Historical Value ($)', 'short_name': 'Issuer'},
                             template="plotly_dark")
            fig_unk.update_layout(yaxis={'categoryorder':'total ascending'})
            # Updated to new 2026 syntax
            st.plotly_chart(fig_unk, width='stretch')
            
        st.write("These CUSIPs could not be translated to a ticker by OpenFIGI.")
        # Updated to new 2026 syntax
        st.dataframe(df_unknowns.style.format({'total_historical_val': '${:,.0f}'}), width='stretch', height=400)
    else:
        st.success("🎉 No unknown CUSIPs!")

# --- DB SIZES ---
st.markdown("---")
st.subheader("3. Database Table Sizes")

# --- FIX: explicitly define tables_list here so the loop can see it ---
tables_list = ['funds', 'holdings', 'company_info', 'stock_prices', 'benchmarks']

cols = st.columns(len(tables_list))
for i, t in enumerate(tables_list):
    cols[i].metric(t, f"{counts.get(t, 0):,}")