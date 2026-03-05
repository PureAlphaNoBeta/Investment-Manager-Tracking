import streamlit as st
import pandas as pd
import plotly.express as px

def render(df_filtered, df_prices, df_bench, ticker_to_name, chart_template):
    st.subheader("Single Stock & Conviction Analysis")
    
    # 1. Preserve full data (including options) for specific lookups
    df_full = df_filtered.copy()
    
    # Filter for Equity Only to exclude options
    df_filtered = df_filtered[df_filtered['put_call'] == 'SHARE'].copy()
    
    # Recalculate weights so they sum to 100% of the Equity Portfolio (excluding options from the denominator)
    df_filtered['Concentration %'] = df_filtered.groupby(['fund_name', 'report_date'])['standardized_market_value'].transform(lambda x: (x / x.sum()) * 100)
    
    stocks = sorted(df_filtered[df_filtered['ticker'] != 'UNKNOWN']['ticker'].unique())
    
    if not stocks: 
        st.warning("No valid stocks available to analyze.")
        return
        
    sel_stock = st.selectbox(
        "Select Stock:", 
        stocks,
        format_func=lambda x: f"{ticker_to_name.get(x, x)} ({x})"
    )
    df_s = df_filtered[df_filtered['ticker'] == sel_stock].copy()
    c_name = ticker_to_name.get(sel_stock, sel_stock)
    
    # --- ROW 1: QUARTERLY SHIFTS ---
    st.markdown("---")
    st.subheader("Quarterly Shifts: Buyers, Sellers & Ownership")
    
    all_qtrs = sorted(df_filtered['report_date'].unique(), reverse=True)
    
    if len(all_qtrs) >= 2:
        sel_qtr_str = st.selectbox("Select Quarter to Analyze Shifts:", [d.strftime('%Y-%m-%d') for d in all_qtrs])
        target_qtr = pd.to_datetime(sel_qtr_str)
        
        prev_qtrs = [q for q in all_qtrs if q < target_qtr]
        
        if prev_qtrs:
            prev_qtr = prev_qtrs[0]
            
            df_latest = df_s[df_s['report_date'] == target_qtr]
            df_prev = df_s[df_s['report_date'] == prev_qtr]
            funds_in_stock = set(df_latest['fund_name']).union(set(df_prev['fund_name']))
            
            shift_data = []
            for f in funds_in_stock:
                s_l = df_latest[df_latest['fund_name'] == f]['shares'].sum() if f in df_latest['fund_name'].values else 0
                s_p = df_prev[df_prev['fund_name'] == f]['shares'].sum() if f in df_prev['fund_name'].values else 0
                w_l = df_latest[df_latest['fund_name'] == f]['Concentration %'].sum() if f in df_latest['fund_name'].values else 0
                w_p = df_prev[df_prev['fund_name'] == f]['Concentration %'].sum() if f in df_prev['fund_name'].values else 0
                
                shift_data.append({
                    'Fund': f,
                    'Delta Shares': s_l - s_p,
                    'Delta Weight %': w_l - w_p,
                })
                
            df_shifts = pd.DataFrame(shift_data)
            
            if df_shifts.empty:
                df_shifts = pd.DataFrame(columns=['Fund', 'Delta Shares', 'Delta Weight %'])
                
            df_buyers = df_shifts[df_shifts['Delta Shares'] > 0].sort_values('Delta Weight %', ascending=False).head(3)
            df_sellers = df_shifts[df_shifts['Delta Shares'] < 0].sort_values('Delta Weight %', ascending=True).head(3)
            
            colA, colB, colC, colD = st.columns(4)
            with colA:
                st.markdown(f"**Ownership Stats ({target_qtr.strftime('%Y-%m-%d')})**")
                valid_owners = df_latest[df_latest['shares'] > 0]
                n_funds = len(valid_owners)
                
                # Equity Shares Stats
                total_equity_shares = valid_owners['shares'].sum()
                net_shares = df_shifts['Delta Shares'].sum()
                net_str = f"{total_equity_shares:,.0f} ({net_shares:+,.0f})"
                
                if not valid_owners.empty:
                    med_w = valid_owners['Concentration %'].median()
                    max_idx = valid_owners['Concentration %'].idxmax()
                    min_idx = valid_owners['Concentration %'].idxmin()
                    
                    max_fund = valid_owners.loc[max_idx, 'fund_name']
                    max_val = valid_owners.loc[max_idx, 'Concentration %']
                    min_fund = valid_owners.loc[min_idx, 'fund_name']
                    min_val = valid_owners.loc[min_idx, 'Concentration %']
                    
                    stat_df = pd.DataFrame({
                        'Metric': ['Funds Owning', 'Median Weight', 'Largest Owner', 'Smallest Owner', 'Total Shares (Equity)'],
                        'Value': [
                            f"{n_funds}",
                            f"{med_w:.2f}%",
                            f"{max_fund} ({max_val:.2f}%)",
                            f"{min_fund} ({min_val:.2f}%)",
                            net_str
                        ]
                    })
                else:
                    stat_df = pd.DataFrame({
                        'Metric': ['Funds Owning', 'Total Shares (Equity)'],
                        'Value': ["0", net_str]
                    })
                
                st.dataframe(stat_df, hide_index=True, width='stretch')
                
            with colB:
                st.markdown("**Top 3 Buyers (vs Previous Qtr)**")
                if not df_buyers.empty:
                    disp_b = df_buyers.copy()
                    disp_b['Delta Shares'] = disp_b['Delta Shares'].map('+{:,.0f}'.format)
                    disp_b['Delta Weight %'] = disp_b['Delta Weight %'].map('+{:.2f}%'.format)
                    st.dataframe(disp_b, hide_index=True, width='stretch')
                else:
                    st.info("No buyers this quarter.")
                    
            with colC:
                st.markdown("**Top 3 Sellers (vs Previous Qtr)**")
                if not df_sellers.empty:
                    disp_s = df_sellers.copy()
                    disp_s['Delta Shares'] = disp_s['Delta Shares'].map('{:,.0f}'.format)
                    disp_s['Delta Weight %'] = disp_s['Delta Weight %'].map('{:.2f}%'.format)
                    st.dataframe(disp_s, hide_index=True, width='stretch')
                else:
                    st.info("No sellers this quarter.")

            with colD:
                st.markdown("**Option Activity**")
                
                # --- Calculate Option Stats from df_full ---
                df_full_stock = df_full[df_full['ticker'] == sel_stock]
                
                # Current Options
                df_opts_curr = df_full_stock[(df_full_stock['report_date'] == target_qtr) & (df_full_stock['put_call'].isin(['Put', 'Call']))]
                # Previous Options
                df_opts_prev = df_full_stock[(df_full_stock['report_date'] == prev_qtr) & (df_full_stock['put_call'].isin(['Put', 'Call']))]
                
                # Calls
                curr_calls = df_opts_curr[df_opts_curr['put_call'] == 'Call']['shares'].sum()
                prev_calls = df_opts_prev[df_opts_prev['put_call'] == 'Call']['shares'].sum()
                delta_calls = curr_calls - prev_calls
                
                # Puts
                curr_puts = df_opts_curr[df_opts_curr['put_call'] == 'Put']['shares'].sum()
                prev_puts = df_opts_prev[df_opts_prev['put_call'] == 'Put']['shares'].sum()
                delta_puts = curr_puts - prev_puts

                opt_rows = []
                if curr_calls > 0 or delta_calls != 0:
                    opt_rows.append({'Metric': 'Total Calls', 'Value': f"{curr_calls:,.0f} ({delta_calls:+,.0f})"})
                if curr_puts > 0 or delta_puts != 0:
                    opt_rows.append({'Metric': 'Total Puts', 'Value': f"{curr_puts:,.0f} ({delta_puts:+,.0f})"})
                
                if opt_rows:
                    st.dataframe(pd.DataFrame(opt_rows), hide_index=True, width='stretch')
                else:
                    st.info("No option activity.")
        else:
            st.info("This is the earliest quarter in the dataset. No previous quarter to compare shifts.")
    else:
        st.info("Not enough history to map quarterly shifts.")

    # --- ROW 2: CONVICTION METRICS ---
    st.markdown("---")
    st.subheader("Conviction Metrics")
    
    # Slider to filter charts
    top_n_funds = st.slider("Max Funds to Display (ranked by Portfolio Weight):", min_value=1, max_value=50, value=5)
    
    # Determine ranking quarter (use selected quarter from above if available, else latest)
    rank_qtr = target_qtr if 'target_qtr' in locals() else all_qtrs[0]
    
    # Identify top funds based on weight in the reference quarter
    ranks = df_s[df_s['report_date'] == rank_qtr].sort_values('Concentration %', ascending=False)
    if ranks.empty:
        # Fallback: if stock not held in reference quarter, rank by max historical weight
        top_funds = df_s.groupby('fund_name')['Concentration %'].max().nlargest(top_n_funds).index.tolist()
    else:
        top_funds = ranks.head(top_n_funds)['fund_name'].tolist()
        
    df_s_plot = df_s[df_s['fund_name'].isin(top_funds)].copy()
    
    c1, c2, c3 = st.columns(3)
    with c1:
        fig_sh = px.line(df_s_plot, x='report_date', y='shares', color='fund_name', markers=True, 
                         title=f'{c_name}: Absolute Shares', template=chart_template)
        st.plotly_chart(fig_sh, width='stretch')
    with c2:
        fig_val = px.line(df_s_plot, x='report_date', y='standardized_market_value', color='fund_name', markers=True, 
                         title=f'{c_name}: Absolute Value ($)', template=chart_template)
        st.plotly_chart(fig_val, width='stretch')
    with c3:
        fig_wt = px.line(df_s_plot, x='report_date', y='Concentration %', color='fund_name', markers=True, 
                         title=f'{c_name}: Portfolio Weight (%)', template=chart_template)
        st.plotly_chart(fig_wt, width='stretch')

    # --- ROW 3: MARKET PRICE VS BENCHMARKS & CALENDAR RETURNS ---
    st.markdown("---")
    st.subheader("Relative Market Performance")
    
    # --- HELPER FUNCTION FOR PERFORMANCE TABLES (Matched to Tab 2 Logic) ---
    def generate_performance_tables(plot_df, main_asset_cols, bench_cols, rename_map, latest_date_override=None):
        def calc_ret(df_t, start_d, end_d, col, strict=False):
            try:
                idx_closest = (df_t['Date'] - start_d).abs().idxmin()
                if strict:
                    closest_date = df_t.loc[idx_closest, 'Date']
                    if abs((closest_date - start_d).days) > 45: return None
                s_val = df_t.loc[idx_closest, col]
                e_val = df_t[df_t['Date'] <= end_d].iloc[-1][col]
                return (e_val / s_val) - 1
            except: return None
        latest_d = latest_date_override if pd.notnull(latest_date_override) else plot_df['Date'].max()
        ytd_d = pd.to_datetime(f"{latest_d.year - 1}-12-31")
        d_1y = latest_d - pd.DateOffset(years=1)
        d_3y = latest_d - pd.DateOffset(years=3)
        d_5y = latest_d - pd.DateOffset(years=5)
        itd_d = plot_df['Date'].min()
        
        asset_cols = main_asset_cols + bench_cols
        assets = [(rename_map.get(c, c), c) for c in asset_cols]
        
        perf_records = []
        for name, col in assets:
            perf_records.append({'Strategy': name, 'YTD': calc_ret(plot_df, ytd_d, latest_d, col), '1Y': calc_ret(plot_df, d_1y, latest_d, col, strict=True), '3Y': calc_ret(plot_df, d_3y, latest_d, col, strict=True), '5Y': calc_ret(plot_df, d_5y, latest_d, col, strict=True), 'ITD': calc_ret(plot_df, itd_d, latest_d, col)})
        df_perf = pd.DataFrame(perf_records)
        for c in ['YTD', '1Y', '3Y', '5Y', 'ITD']: df_perf[c] = df_perf[c].apply(lambda x: f"{x*100:+.1f}%" if pd.notnull(x) else "N/A")
        
        cal_years = list(range(latest_d.year - 5, latest_d.year))
        cal_records = []
        for name, col in assets:
            record = {'Strategy': name}
            for yr in sorted(cal_years, reverse=True):
                start, end = pd.to_datetime(f"{yr-1}-12-31"), pd.to_datetime(f"{yr}-12-31")
                record[str(yr)] = calc_ret(plot_df, start, end, col)
            cal_records.append(record)
        df_cal = pd.DataFrame(cal_records)
        for yr in sorted(cal_years, reverse=True): df_cal[str(yr)] = df_cal[str(yr)].apply(lambda x: f"{x*100:+.1f}%" if pd.notnull(x) else "N/A")
        
        st.write("**Trailing Returns**"); st.dataframe(df_perf.set_index('Strategy'), use_container_width=True)
        st.write("**Calendar Year Returns**"); st.dataframe(df_cal.set_index('Strategy'), use_container_width=True)

    dp = df_prices[df_prices['ticker'] == sel_stock].copy()
    
    if dp.empty:
        st.warning("No price data available for this specific asset.")
    elif df_bench.empty:
        st.warning("Benchmark data missing from database. Cannot compare.")
    else:
        dp = dp.sort_values('Date')
        bench_df = df_bench.sort_values('Date').copy()
        
        bench_cols = []
        rename_map = {}
        
        if 'SPY' in bench_df.columns:
            bench_cols.append('SPY')
            rename_map['SPY'] = 'S&P 500'
        if 'URTH' in bench_df.columns:
            bench_cols.append('URTH')
            rename_map['URTH'] = 'MSCI World'
        elif 'MSCI' in bench_df.columns:
            bench_cols.append('MSCI')
            rename_map['MSCI'] = 'MSCI World'
        
        if not bench_cols:
            st.warning("Could not find SPY or URTH/MSCI columns in your benchmarks table.")
        else:
            table_df = pd.merge_asof(
                dp[['Date', 'price']].rename(columns={'price': c_name}), 
                bench_df[['Date'] + bench_cols], 
                on='Date', direction='nearest'
            ).dropna()

            if not table_df.empty:
                # Create a separate df for plotting and index the values
                plot_df = table_df.copy()
                plot_df[c_name] = (plot_df[c_name] / plot_df[c_name].iloc[0]) * 100
                for col in bench_cols:
                    # Create display column for chart
                    plot_df[rename_map[col]] = (plot_df[col] / plot_df[col].iloc[0]) * 100
                    
                plot_vars = [c_name] + list(rename_map.values())
                melt_plot = plot_df.melt(id_vars=['Date'], value_vars=plot_vars, 
                                         var_name='Asset', value_name='Indexed Price (Base 100)')
                
                latest_d = df_prices['Date'].max()
                fig_pr = px.line(melt_plot, x='Date', y='Indexed Price (Base 100)', color='Asset', 
                                 title=f"{c_name} vs Benchmarks (as of {latest_d.strftime('%Y-%m-%d')})", template=chart_template)
                fig_pr.update_traces(line=dict(width=2)) 
                st.plotly_chart(fig_pr, width='stretch')
                
                # Generate Tables using the un-indexed, raw data
                generate_performance_tables(table_df, [c_name], bench_cols, rename_map, latest_date_override=latest_d)

    # --- ROW 4: HISTORICAL LEDGER TABLE ---
    st.markdown("---")
    st.subheader("Historical Equity Ownership")
    
    ledger_metric = st.radio("Display Metric:", ["Shares", "Market Value ($)"], horizontal=True)
    
    hist_df = df_s[['report_date', 'fund_name', 'shares', 'standardized_market_value']].copy()
    hist_df['report_date'] = hist_df['report_date'].dt.strftime('%Y-%m-%d')
    
    val_col = 'shares' if ledger_metric == "Shares" else 'standardized_market_value'
    
    pivot_df = hist_df.pivot_table(index='report_date', columns='fund_name', values=val_col, aggfunc='sum').fillna(0)
    pivot_df = pivot_df.sort_index(ascending=False)
    
    for col in pivot_df.columns:
        if ledger_metric == "Shares":
            pivot_df[col] = pivot_df[col].apply(lambda x: f"{x:,.0f}" if x > 0 else "-")
        else:
            pivot_df[col] = pivot_df[col].apply(lambda x: f"${x:,.0f}" if x > 0 else "-")
    
    pivot_df.index.name = 'Quarter'
    st.dataframe(pivot_df, width='stretch')