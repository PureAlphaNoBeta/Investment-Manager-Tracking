import streamlit as st
import pandas as pd
import plotly.express as px
import numpy as np

def render(df_cum, df_shadow, df_contrib, df_bench, df_equities, selected_funds, chart_template, df_valid, df_prices):
    st.subheader("Performance & Shadow Trader Backtest")
    
    col_f1, col_f2 = st.columns([1, 2])
    with col_f1:
        sel_perf_fund = st.selectbox("Select Manager to Audit:", selected_funds)
    with col_f2:
        # The switch to instantly exclude synthetic prices and recalculate
        st.write("") # Spacing
        exclude_synthetic = st.toggle("Exclude Synthetic Prices")

    if not sel_perf_fund:
        return

    # --- 1. DYNAMIC RECALCULATION ENGINE ---
    if exclude_synthetic:
        # Filter out synthetic tickers for this specific manager
        # Explicitly ensure only SHARES are used (redundant if app.py is correct, but safe)
        fund_valid = df_valid[(df_valid['fund_name'] == sel_perf_fund) & (~df_valid['ticker'].str.startswith('SYN_')) & (df_valid['put_call'] == 'SHARE')].copy()
        
        # Re-normalize portfolio weights so they still add up to 100%
        fund_valid['adjusted_weight'] = fund_valid.groupby('report_date')['standardized_market_value'].transform(lambda x: x / x.sum())
        
        quarters = sorted(fund_valid['report_date'].unique())
        c_data, ctr_data = [], []
        cum_ret = 1.0 
        
        for i in range(len(quarters) - 1):
            cq, nq = quarters[i], quarters[i+1]
            pq = fund_valid[fund_valid['report_date'] == cq]
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
                ctr_data.append({'Fund': sel_perf_fund, 'Ticker': r['ticker'], 'Company': r['name_of_issuer'], 'Contrib': r['contrib']})
            
            q_ret = p_rets['contrib'].sum()
            cum_ret *= (1 + q_ret)
            c_data.append({'Fund': sel_perf_fund, 'Date': nq, 'Cum_Ret': cum_ret, 'Q_Ret': q_ret})
            
        fc = pd.DataFrame(c_data)
        fc_ctr = pd.DataFrame(ctr_data)
    else:
        fc = df_cum[df_cum['Fund'] == sel_perf_fund].copy()
        fc_ctr = df_contrib[df_contrib['Fund'] == sel_perf_fund].copy()

    if fc.empty:
        st.warning("Insufficient pricing data to chart performance for this manager.")
        return

    # Prepare Dates & Benchmarks
    fc['Date'] = pd.to_datetime(fc['Date'])
    fc.sort_values('Date', inplace=True)
    fc['YM'] = fc['Date'].dt.to_period('M')
    
    if not df_bench.empty:
        df_bench['YM'] = pd.to_datetime(df_bench['Date']).dt.to_period('M')
        fc = pd.merge(fc, df_bench[['YM', 'SPY', '^IRX']], on='YM', how='left')
        fc['SPY_Ret'] = fc['SPY'].pct_change()
        fc['Rf_Q'] = (fc['^IRX'].shift(1) / 100) / 4
        fc['Rf_Q'] = fc['Rf_Q'].fillna(0)
        calc_df = fc.dropna(subset=['SPY_Ret']).copy()
    else:
        calc_df = fc.copy()
        calc_df['SPY_Ret'], calc_df['Rf_Q'] = 0, 0

    # Risk Metrics Calculation
    qr = calc_df['Q_Ret']
    tq = len(fc)
    itd = fc['Cum_Ret'].iloc[-1] - 1
    ann = ((1 + itd) ** (4 / tq)) - 1 if tq > 0 else 0
    vol = qr.std() * np.sqrt(4) if len(qr) > 1 else 0.0
    if pd.isna(vol): vol = 0.0

    fc['Peak'] = fc['Cum_Ret'].cummax()
    mdd = ((fc['Cum_Ret'] - fc['Peak']) / fc['Peak']).min()
    if pd.isna(mdd): mdd = 0.0
    
    sharpe, beta, alpha = 0.0, 1.0, 0.0
    if len(calc_df) > 1 and not df_bench.empty:
        ex = calc_df['Q_Ret'] - calc_df['Rf_Q']
        ex_std = ex.std()
        if pd.notna(ex_std) and ex_std > 0:
            sharpe = (ex.mean() / ex_std) * np.sqrt(4)
            
        var = calc_df['SPY_Ret'].var()
        cov = calc_df['Q_Ret'].cov(calc_df['SPY_Ret'])
        if pd.notna(var) and var > 0 and pd.notna(cov):
            beta = cov / var
            
        yrs = tq / 4
        if yrs > 0:
            spy_cum = (1 + calc_df['SPY_Ret']).cumprod()
            if not spy_cum.empty:
                ann_spy = (spy_cum.iloc[-1])**(1/yrs) - 1
                ann_rf = calc_df['Rf_Q'].mean() * 4
                alpha = ann - (ann_rf + beta * (ann_spy - ann_rf))
                
    if pd.isna(alpha): alpha = 0.0
    if pd.isna(beta): beta = 1.0
    if pd.isna(sharpe): sharpe = 0.0

    # UI: Risk Metrics
    st.markdown("---")
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("ITD Return", f"{itd*100:.1f}%")
    c2.metric("Ann. Return", f"{ann*100:.1f}%")
    c3.metric("Ann. Volatility", f"{vol*100:.1f}%")
    c4.metric("Sharpe Ratio", f"{sharpe:.2f}")
    c5.metric("Max Drawdown", f"{mdd*100:.1f}%")
    
    sc1, sc2, sc3 = st.columns(3)
    sc1.metric("Beta (vs SPY)", f"{beta:.2f}")
    sc2.metric("Jensen's Alpha", f"{alpha*100:+.2f}%")

    # UI: Attribution
    st.markdown("---")
    st.write("### Track Record Attribution: Top Drivers & Drags")
    if not fc_ctr.empty:
        fc_ctr_grp = fc_ctr.groupby(['Ticker', 'Company'])['Contrib'].sum().reset_index().sort_values('Contrib', ascending=False)
        t5, b5 = fc_ctr_grp.head(5).copy(), fc_ctr_grp.tail(5).copy().sort_values('Contrib', ascending=True)
        t5['Ticker'] = t5['Ticker'].apply(lambda x: f"⚠️ {x}" if x.startswith('SYN_') else x)
        b5['Ticker'] = b5['Ticker'].apply(lambda x: f"⚠️ {x}" if x.startswith('SYN_') else x)
        t5['Contrib'] = t5['Contrib'].apply(lambda x: f"+{x*100:.2f}%")
        b5['Contrib'] = b5['Contrib'].apply(lambda x: f"{x*100:.2f}%")
        
        ct, cb = st.columns(2)
        ct.write("🚀 **Top Drivers**"); ct.dataframe(t5.set_index('Ticker')[['Company', 'Contrib']], width='stretch')
        cb.write("⚓ **Top Drags**"); cb.dataframe(b5.set_index('Ticker')[['Company', 'Contrib']], width='stretch')

    # --- HELPER FUNCTION FOR PERFORMANCE TABLES ---
    def generate_performance_tables(plot_df, assets, latest_date_override=None):
        def calc_ret(df_t, start_d, end_d, col, strict=False):
            try:
                idx_closest = (df_t['Date'] - start_d).abs().idxmin()
                if strict:
                    closest_date = df_t.loc[idx_closest, 'Date']
                    if abs((closest_date - start_d).days) > 45: return None
                s_val = df_t.loc[idx_closest, col]
                e_val = df_t[df_t['Date'] <= end_d].iloc[-1][col]
                return (e_val / s_val) - 1
            except:
                return None
                
        latest_d = latest_date_override if pd.notnull(latest_date_override) else plot_df['Date'].max()
        ytd_d = pd.to_datetime(f"{latest_d.year - 1}-12-31")
        
        # Calendar
        cal_years = list(range(latest_d.year - 5, latest_d.year))
        cal_records = []
        for name, col in assets:
            record = {'Strategy': name}
            record['YTD'] = calc_ret(plot_df, ytd_d, latest_d, col)
            for yr in sorted(cal_years, reverse=True):
                start, end = pd.to_datetime(f"{yr-1}-12-31"), pd.to_datetime(f"{yr}-12-31")
                record[str(yr)] = calc_ret(plot_df, start, end, col)
            cal_records.append(record)
        df_cal = pd.DataFrame(cal_records)
        
        cols_to_fmt = [c for c in df_cal.columns if c != 'Strategy']
        for c in cols_to_fmt:
            df_cal[c] = df_cal[c].apply(lambda x: f"{x*100:+.1f}%" if pd.notnull(x) else "N/A")
            
        st.write("**Calendar Year Returns**")
        st.dataframe(df_cal.set_index('Strategy'), use_container_width=True)

    # Prepare Benchmarks Mapping
    bench_cols = []
    rename_map = {}
    if not df_bench.empty:
        if 'SPY' in df_bench.columns: bench_cols.append('SPY'); rename_map['SPY'] = 'S&P 500'
        if 'URTH' in df_bench.columns: bench_cols.append('URTH'); rename_map['URTH'] = 'MSCI World'
        elif 'MSCI' in df_bench.columns: bench_cols.append('MSCI'); rename_map['MSCI'] = 'MSCI World'

    # ==========================================
    # COMBINED CHART: ACTUAL + SHADOW + BENCHMARKS
    # ==========================================
    st.markdown("---")
    latest_d = df_prices['Date'].max()
    st.subheader(f"Track Record Analysis: {sel_perf_fund} (as of {latest_d.strftime('%Y-%m-%d')})")
    
    # 1. Actual
    plot_df = fc[['Date', 'Cum_Ret']].copy()
    plot_df.rename(columns={'Cum_Ret': sel_perf_fund}, inplace=True)
    plot_df[sel_perf_fund] = plot_df[sel_perf_fund] * 100 # Base 100
    
    # 2. Benchmarks
    df_b_sub = df_bench[['Date'] + bench_cols].copy() if not df_bench.empty else pd.DataFrame(columns=['Date'])
    df_b_sub['Date'] = pd.to_datetime(df_b_sub['Date'])
    
    # Merge All
    table_merged = pd.merge_asof(plot_df.sort_values('Date'), df_b_sub.sort_values('Date'), on='Date', direction='nearest')
    table_merged = table_merged.dropna(subset=[sel_perf_fund])
    
    if not table_merged.empty:
        # Rebase Benchmarks
        for c in bench_cols:
            if table_merged[c].iloc[0] != 0:
                table_merged[c] = (table_merged[c] / table_merged[c].iloc[0]) * table_merged[sel_perf_fund].iloc[0]
            
        assets_to_plot = [sel_perf_fund]
        
        display_assets = []
        for a in assets_to_plot: display_assets.append((a, a))
        for b in bench_cols: display_assets.append((rename_map.get(b, b), b))
        
        plot_vars = assets_to_plot + bench_cols
        melted = table_merged.melt(id_vars=['Date'], value_vars=plot_vars, var_name='Strategy', value_name='Indexed (Base 100)')
        melted['Strategy'] = melted['Strategy'].map(lambda x: rename_map.get(x, x))
        
        fig = px.line(melted, x='Date', y='Indexed (Base 100)', color='Strategy', template=chart_template)
        st.plotly_chart(fig, use_container_width=True)
        
        generate_performance_tables(table_merged, display_assets, latest_date_override=latest_d)
        
        # Quarterly Returns Table
        st.markdown("---")
        with st.expander("Quarterly Returns (ITD)", expanded=False):
            q_df = table_merged[['Date'] + plot_vars].copy()
            q_df.set_index('Date', inplace=True)
            q_rets = q_df.pct_change().dropna(how='all')
            q_rets.rename(columns=rename_map, inplace=True)
            
            for c in q_rets.columns:
                q_rets[c] = q_rets[c].apply(lambda x: f"{x*100:+.2f}%" if pd.notnull(x) else "")
            
            q_rets.sort_index(ascending=False, inplace=True)
            st.dataframe(q_rets, use_container_width=True)