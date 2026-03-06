import streamlit as st
import pandas as pd
import plotly.express as px
import numpy as np

def render(df_filtered, df_raw, ticker_to_name, chart_template, df_valid, df_prices, df_bench):
    """
    Renders the Universe Overview tab with advanced, interactive analytics.
    """
    st.subheader("Universe Snapshot")

    # --- Data Preparation and Filters ---
    df_shares = df_filtered[df_filtered['put_call'] == 'SHARE'].copy()

    if df_shares.empty:
        st.warning("No share data available for the selected filters.")
        return

    all_qtrs = sorted(df_shares['report_date'].unique(), reverse=True)

    if len(all_qtrs) < 1:
        st.warning("Not enough historical data to display overview.")
        return

    # --- Controls: Quarter and Companies to Display ---
    c1, c2, c3 = st.columns([2, 2, 1])
    with c1:
        selected_qtr_str = st.selectbox(
            "Select Quarter",
            [d.strftime('%Y-%m-%d') for d in all_qtrs],
            key="universe_qtr_select"
        )
        selected_qtr = pd.to_datetime(selected_qtr_str)

    with c3:
        n_companies = st.slider(
            "Top N Companies to Display",
            min_value=3,
            max_value=30,
            value=10,
            key="n_companies_slider"
        )

    # --- Filter data based on selected quarter ---
    df_selected = df_shares[df_shares['report_date'] == selected_qtr].copy()
    if df_selected.empty:
        st.warning(f"No data available for the selected quarter: {selected_qtr_str}")
        return

    # --- Layout ---
    st.markdown("---")

    # --- Most Crowded Longs (Bubble Chart) ---
    st.markdown("##### Most Crowded Longs")

    # Aggregate stats for crowding
    crowding_stats = df_selected.groupby('ticker').agg(
        num_owners=('fund_name', 'nunique'),
        median_weight=('Concentration %', 'median'),
        sector=('sector', 'first')
    ).reset_index()

    # Find min/max owners for hover. Using apply for simplicity with complex return.
    def get_owner_stats(group):
        max_owner_row = group.loc[group['standardized_market_value'].idxmax()]
        min_owner_row = group.loc[group['standardized_market_value'].idxmin()]
        return pd.Series({
            'max_owner_fund': max_owner_row['fund_name'],
            'max_owner_size': max_owner_row['standardized_market_value'],
            'min_owner_fund': min_owner_row['fund_name'],
            'min_owner_size': min_owner_row['standardized_market_value'],
        })

    if not df_selected.empty:
        owner_details = df_selected.groupby('ticker').apply(get_owner_stats).reset_index()
        bubble_df = pd.merge(crowding_stats, owner_details, on='ticker')
        bubble_df['Company'] = bubble_df['ticker'].map(ticker_to_name).fillna(bubble_df['ticker'])
        bubble_df = bubble_df.nlargest(n_companies, 'num_owners')

        if not bubble_df.empty:
            fig_bubble = px.scatter(
                bubble_df, x="num_owners", y="median_weight", size="num_owners", color="sector",
                hover_name="Company", custom_data=['max_owner_fund', 'max_owner_size', 'min_owner_fund', 'min_owner_size'],
                template=chart_template, title="Crowding: # Owners vs. Median Weight"
            )
            fig_bubble.update_traces(
                hovertemplate="<br>".join([
                    "<b>%{hovertext}</b>", "Owners: %{x}", "Median Weight: %{y:.2f}%", "<hr>",
                    "Largest Holder: %{customdata[0]} (%{customdata[1]:$,.0f})",
                    "Smallest Holder: %{customdata[2]} (%{customdata[3]:$,.0f})",
                    "<extra></extra>"
                ])
            )
            fig_bubble.update_layout(xaxis_title="Number of Funds", yaxis_title="Median Portfolio Weight (%)")
            st.plotly_chart(fig_bubble, use_container_width=True)
        else:
            st.info("No crowding data to display.")
    else:
        st.info("No data for selected quarter.")

    st.markdown("---")
    col1, col2 = st.columns(2)

    # --- Column 2 & 3: Net Buying and Selling (Weight-Based) ---
    qtr_index = all_qtrs.index(selected_qtr)
    if qtr_index + 1 >= len(all_qtrs):
        with col1: st.info("No previous quarter for trend analysis.")
        with col2: st.info("No previous quarter for trend analysis.")
    else:
        prev_qtr = all_qtrs[qtr_index + 1]
        df_prev = df_shares[df_shares['report_date'] == prev_qtr].copy()

        # 1. Calculate Universe AUM for both quarters
        all_funds_in_period = set(df_selected['fund_name'].unique()) | set(df_prev['fund_name'].unique())
        aum_selected = df_filtered[(df_filtered['fund_name'].isin(all_funds_in_period)) & (df_filtered['report_date'] == selected_qtr)].drop_duplicates(subset='fund_name')['Total AUM'].sum()
        aum_prev = df_filtered[(df_filtered['fund_name'].isin(all_funds_in_period)) & (df_filtered['report_date'] == prev_qtr)].drop_duplicates(subset='fund_name')['Total AUM'].sum()

        if aum_selected == 0 or aum_prev == 0:
            st.warning("Cannot calculate universe trends due to missing AUM data.")
            return

        # 2. Calculate total value for each ticker
        total_val_selected = df_selected.groupby('ticker')['standardized_market_value'].sum()
        total_val_prev = df_prev.groupby('ticker')['standardized_market_value'].sum()

        # 3. Calculate universe weight
        weight_selected = total_val_selected / aum_selected
        weight_prev = total_val_prev / aum_prev

        # 4. Calculate delta weight
        delta_weight = (weight_selected.subtract(weight_prev, fill_value=0) * 100).sort_values(ascending=False)
        delta_weight_df = delta_weight.reset_index()
        delta_weight_df.columns = ['ticker', 'delta_weight_pct']
        delta_weight_df['Company'] = delta_weight_df['ticker'].map(ticker_to_name).fillna(delta_weight_df['ticker'])

        # 5. Get top mover info
        def get_top_mover(group, period_df, period_str):
            df = period_df[period_df['ticker'] == group['ticker']]
            if not df.empty:
                top_mover = df.loc[df['Concentration %'].idxmax()]
                return f"{top_mover['fund_name']} ({top_mover['Concentration %']:.2f}%)"
            return "N/A"

        with col1:
            st.markdown("##### Most Bought (Δ Universe Weight)")
            most_bought = delta_weight_df.nlargest(n_companies, 'delta_weight_pct')
            if not most_bought.empty:
                fig_bought = px.bar(most_bought, x='delta_weight_pct', y='Company', orientation='h', template=chart_template, color_discrete_sequence=['#22c55e'])
                fig_bought.update_traces(hovertemplate="%{y}: +%{x:.3f}%<extra></extra>")
                fig_bought.update_layout(yaxis={'categoryorder':'total ascending'}, yaxis_title=None, xaxis_title="Change in Universe Weight (%)")
                st.plotly_chart(fig_bought, use_container_width=True)
            else:
                st.info("No net buying activity.")

        with col2:
            st.markdown("##### Most Sold (Δ Universe Weight)")
            most_sold = delta_weight_df.nsmallest(n_companies, 'delta_weight_pct')
            if not most_sold.empty:
                fig_sold = px.bar(most_sold, x='delta_weight_pct', y='Company', orientation='h', template=chart_template, color_discrete_sequence=['#ef4444'])
                fig_sold.update_traces(hovertemplate="%{y}: %{x:.3f}%<extra></extra>")
                fig_sold.update_layout(yaxis={'categoryorder':'total descending'}, yaxis_title=None, xaxis_title="Change in Universe Weight (%)")
                st.plotly_chart(fig_sold, use_container_width=True)
            else:
                st.info("No net selling activity.")

    # --- Holding Period Analysis (from former Conviction Tab) ---
    st.markdown("---")
    st.subheader("Holding Period Analysis")
    l_dates = df_shares.groupby('fund_name')['report_date'].max().reset_index()
    h_sum = df_shares.groupby(['fund_name', 'ticker']).agg(
        F_Qtr=('report_date', 'min'), L_Qtr=('report_date', 'max'), Qtrs=('report_date', 'nunique')
    ).reset_index()
    h_sum = pd.merge(h_sum, l_dates, on='fund_name', how='left')
    h_sum['Status'] = h_sum.apply(lambda x: 'Open' if x['L_Qtr'] == x['report_date'] else 'Closed', axis=1)

    fig_bx = px.box(h_sum, x='fund_name', y='Qtrs', color='Status', title="Holding Period Distribution", template=chart_template)
    st.plotly_chart(fig_bx, use_container_width=True)

    st.markdown("---")
    st.subheader("Crowded Index Backtest")

    # --- Fund Selection for Backtest ---
    all_funds = sorted(df_raw['fund_name'].unique())
    default_funds = ["TCI Fund Management", "Sachem Head", "Hengistbury Investment Partners", "Foxhaven Asset Management", "Slate Path Capital", "Egerton Capital"]
    default_funds = [f for f in default_funds if f in all_funds]

    selected_backtest_funds = st.multiselect(
        "Select up to 10 funds for the crowded index backtest:",
        options=all_funds,
        default=default_funds,
        max_selections=10,
        key="crowded_backtest_funds"
    )
    st.markdown('''
    **How the Crowded Index Works:**
    * **Universe:** We look at regular stock shares (not options) held by the funds you selected above.
    * **Ranking:** Stocks are scored based on two main factors:
        1. **Popularity:** How many of the selected funds own the stock.
        2. **Conviction:** The average size of the position relative to the funds' total assets.
    * **Selection:** We combine these two scores. The 5 stocks with the best overall score (highest popularity and conviction combined) are chosen as the "Crowded Index" for that quarter.
    * **Performance:** We then calculate the returns as if we invested an equal amount of money into each of these 5 stocks. The **Shadow Index** shows what happens if you bought those same 5 stocks, but waited 60 days after the quarter ended to buy them.
    ''')

    if not selected_backtest_funds:
        st.info("Please select at least one fund to run the backtest.")
    else:
        # --- Crowded Index Identification ---
        backtest_df = df_raw[df_raw['fund_name'].isin(selected_backtest_funds) & (df_raw['put_call'] == 'SHARE')].copy()
        valid_tkrs = df_prices['ticker'].unique()
        backtest_df['has_price'] = backtest_df['ticker'].isin(valid_tkrs)
        backtest_valid_df = backtest_df[backtest_df['has_price']].copy()

        if backtest_valid_df.empty:
            st.warning("No valid stock data with prices available for the selected funds.")
        else:
            q_v_aum = backtest_valid_df.groupby(['report_date', 'fund_name'])['standardized_market_value'].sum().reset_index(name='V_AUM')
            if q_v_aum.empty:
                st.warning("Could not calculate AUM for the selected funds.")
            else:
                backtest_valid_df = pd.merge(backtest_valid_df, q_v_aum, on=['report_date', 'fund_name'])
                backtest_valid_df['adjusted_weight'] = backtest_valid_df['standardized_market_value'] / backtest_valid_df['V_AUM']

                quarters = sorted(backtest_valid_df['report_date'].unique())
                top_5_crowded_quarterly = []

                for quarter in quarters:
                    df_q = backtest_valid_df[backtest_valid_df['report_date'] == quarter]
                    if df_q.empty: continue

                    crowd_by_owners = df_q.groupby('ticker')['fund_name'].nunique().reset_index()
                    crowd_by_owners.rename(columns={'fund_name': 'num_owners'}, inplace=True)
                    crowd_by_owners['owner_rank'] = crowd_by_owners['num_owners'].rank(ascending=False, method='min')

                    crowd_by_weight = df_q.groupby('ticker')['adjusted_weight'].mean().reset_index()
                    crowd_by_weight.rename(columns={'adjusted_weight': 'avg_weight'}, inplace=True)
                    crowd_by_weight['weight_rank'] = crowd_by_weight['avg_weight'].rank(ascending=False, method='min')

                    combined_ranks = pd.merge(crowd_by_owners, crowd_by_weight, on='ticker')
                    combined_ranks['total_rank'] = combined_ranks['owner_rank'] + combined_ranks['weight_rank']

                    top_5 = combined_ranks.sort_values('total_rank', ascending=True).head(5)
                    top_5_tickers = top_5['ticker'].tolist()

                    top_5_with_names = [f"{t} ({ticker_to_name.get(t, 'N/A')})" for t in top_5_tickers]
                    top_5_crowded_quarterly.append({
                        "report_date": quarter,
                        "top_5_tickers": top_5_tickers,
                        "top_5_display": top_5_with_names
                    })

                if not top_5_crowded_quarterly:
                    st.warning("Could not determine crowded stocks for the selected funds.")
                else:
                    def calculate_crowded_index_performance(_top_5_crowded_quarterly, _df_prices):
                        quarters_map = {d['report_date']: d['top_5_tickers'] for d in _top_5_crowded_quarterly}
                        quarters = sorted(quarters_map.keys())
                        cum_data, s_data = [], []
                        latest_price_date = _df_prices['Date'].max()
                        cum_ret, s_cum = 1.0, 1.0

                        for i in range(len(quarters) - 1):
                            cq, nq = quarters[i], quarters[i+1]
                            tkrs = quarters_map[cq]
                            if not tkrs: continue
                            p_start = _df_prices[(_df_prices['Date'] >= cq) & (_df_prices['ticker'].isin(tkrs))].groupby('ticker').first().reset_index()
                            p_end = _df_prices[(_df_prices['Date'] >= nq) & (_df_prices['ticker'].isin(tkrs))].groupby('ticker').first().reset_index()
                            if p_start.empty or p_end.empty or len(p_start) != len(p_end): continue

                            rets = pd.merge(p_start[['ticker', 'price']], p_end[['ticker', 'price']], on='ticker', suffixes=('_s', '_e'))
                            rets['ret'] = (rets['price_e'] - rets['price_s']) / rets['price_s']
                            q_ret = rets['ret'].mean()
                            cum_ret *= (1 + q_ret)
                            cum_data.append({'Date': nq, 'Cum_Ret': cum_ret, 'Q_Ret': q_ret})
                            sq_s, sq_e = cq + pd.DateOffset(months=2), nq + pd.DateOffset(months=2)
                            ps_s = _df_prices[(_df_prices['Date'] >= sq_s) & (_df_prices['ticker'].isin(tkrs))].groupby('ticker').first().reset_index()
                            ps_e = _df_prices[(_df_prices['Date'] >= sq_e) & (_df_prices['ticker'].isin(tkrs))].groupby('ticker').first().reset_index()
                            if not ps_s.empty and not ps_e.empty and len(ps_s) == len(ps_e):
                                rs = pd.merge(ps_s[['ticker', 'price']], ps_e[['ticker', 'price']], on='ticker', suffixes=('_s','_e'))
                                rs['ret'] = (rs['price_e'] - rs['price_s']) / rs['price_s']
                                s_cum *= (1 + rs['ret'].mean())
                            s_data.append({'Date': nq, 'Actual %': (cum_ret-1)*100, 'Shadow %': (s_cum-1)*100})

                        if len(quarters) > 0 and latest_price_date > quarters[-1]:
                            last_q = quarters[-1]
                            tkrs = quarters_map.get(last_q)
                            if tkrs:
                                p_start = _df_prices[(_df_prices['Date'] >= last_q) & (_df_prices['ticker'].isin(tkrs))].groupby('ticker').first().reset_index()
                                p_end = _df_prices[(_df_prices['Date'] == latest_price_date) & (_df_prices['ticker'].isin(tkrs))].groupby('ticker').first().reset_index()
                                if not p_start.empty and not p_end.empty and len(p_start) == len(p_end):
                                    rets = pd.merge(p_start[['ticker', 'price']], p_end[['ticker', 'price']], on='ticker', suffixes=('_s', '_e'))
                                    rets['ret'] = (rets['price_e'] - rets['price_s']) / rets['price_s']
                                    q_ret = rets['ret'].mean()
                                    cum_ret *= (1 + q_ret)
                                    cum_data.append({'Date': latest_price_date, 'Cum_Ret': cum_ret, 'Q_Ret': q_ret})
                                    sq_s = last_q + pd.DateOffset(months=2)
                                    if latest_price_date > sq_s:
                                        ps_s = _df_prices[(_df_prices['Date'] >= sq_s) & (_df_prices['ticker'].isin(tkrs))].groupby('ticker').first().reset_index()
                                        ps_e = _df_prices[(_df_prices['Date'] == latest_price_date) & (_df_prices['ticker'].isin(tkrs))].groupby('ticker').first().reset_index()
                                        if not ps_s.empty and not ps_e.empty and len(ps_s) == len(ps_e):
                                            rs = pd.merge(ps_s[['ticker', 'price']], ps_e[['ticker', 'price']], on='ticker', suffixes=('_s','_e'))
                                            s_cum *= (1 + (rs['ret'].mean()))
                                    s_data.append({'Date': latest_price_date, 'Actual %': (cum_ret-1)*100, 'Shadow %': (s_cum-1)*100})
                        return pd.DataFrame(cum_data), pd.DataFrame(s_data)

                    df_crowded_cum, df_crowded_shadow = calculate_crowded_index_performance(top_5_crowded_quarterly, df_prices)

                    if df_crowded_cum.empty:
                        st.warning("Could not calculate performance for the crowded index.")
                    else:
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

                        df_crowded_cum['Date'] = pd.to_datetime(df_crowded_cum['Date']); df_crowded_cum.sort_values('Date', inplace=True); df_crowded_cum['YM'] = df_crowded_cum['Date'].dt.to_period('M')
                        if not df_bench.empty:
                            df_bench['YM'] = pd.to_datetime(df_bench['Date']).dt.to_period('M')
                            bench_cols_available = [c for c in ['SPY', '^IRX'] if c in df_bench.columns]
                            calc_df = pd.merge(df_crowded_cum, df_bench[['YM'] + bench_cols_available], on='YM', how='left')
                            if 'SPY' in calc_df.columns: calc_df['SPY_Ret'] = calc_df['SPY'].pct_change()
                            if '^IRX' in calc_df.columns: calc_df['Rf_Q'] = (calc_df['^IRX'].shift(1) / 100) / 4
                            calc_df = calc_df.fillna(0)
                        else:
                            calc_df = df_crowded_cum.copy(); calc_df['SPY_Ret'], calc_df['Rf_Q'] = 0, 0

                        qr, tq = calc_df['Q_Ret'], len(df_crowded_cum)
                        itd = df_crowded_cum['Cum_Ret'].iloc[-1] - 1
                        ann = ((1 + itd) ** (4 / tq)) - 1 if tq > 0 else 0
                        vol = qr.std() * np.sqrt(4) if len(qr) > 1 else 0.0; vol = 0.0 if pd.isna(vol) else vol
                        df_crowded_cum['Peak'] = df_crowded_cum['Cum_Ret'].cummax(); mdd = ((df_crowded_cum['Cum_Ret'] - df_crowded_cum['Peak']) / df_crowded_cum['Peak']).min(); mdd = 0.0 if pd.isna(mdd) else mdd
                        sharpe, beta, alpha = 0.0, 1.0, 0.0
                        if 'SPY_Ret' in calc_df.columns and len(calc_df) > 1 and not df_bench.empty:
                            ex = calc_df['Q_Ret'] - calc_df['Rf_Q']; ex_std = ex.std()
                            if pd.notna(ex_std) and ex_std > 0: sharpe = (ex.mean() / ex_std) * np.sqrt(4)
                            var, cov = calc_df['SPY_Ret'].var(), calc_df['Q_Ret'].cov(calc_df['SPY_Ret'])
                            if pd.notna(var) and var > 0 and pd.notna(cov): beta = cov / var
                            yrs = tq / 4
                            if yrs > 0:
                                spy_cum = (1 + calc_df['SPY_Ret']).cumprod()
                                if not spy_cum.empty:
                                    ann_spy = (spy_cum.iloc[-1])**(1/yrs) - 1
                                    ann_rf = calc_df['Rf_Q'].mean() * 4
                                    alpha = ann - (ann_rf + beta * (ann_spy - ann_rf))
                        alpha = 0.0 if pd.isna(alpha) else alpha
                        beta = 1.0 if pd.isna(beta) else beta
                        sharpe = 0.0 if pd.isna(sharpe) else sharpe
                        st.markdown("---"); c1, c2, c3, c4, c5 = st.columns(5); c1.metric("ITD Return", f"{itd*100:.1f}%"); c2.metric("Ann. Return", f"{ann*100:.1f}%"); c3.metric("Ann. Volatility", f"{vol*100:.1f}%"); c4.metric("Sharpe Ratio", f"{sharpe:.2f}"); c5.metric("Max Drawdown", f"{mdd*100:.1f}%")
                        sc1, sc2, sc3 = st.columns(3); sc1.metric("Beta (vs SPY)", f"{beta:.2f}"); sc2.metric("Jensen's Alpha", f"{alpha*100:+.2f}%")
                        if not df_crowded_shadow.empty: act, shd = df_crowded_shadow['Actual %'].iloc[-1], df_crowded_shadow['Shadow %'].iloc[-1]; sc3.metric("Alpha Bleed (60-Day Lag)", f"{act - shd:+.1f}%", delta_color="inverse")

                        bench_cols, rename_map = [], {}
                        rename_map['Crowded Index'] = 'Crowded Index'
                        rename_map['Crowded Index (Shadow)'] = 'Crowded Index (Shadow)'

                        if not df_bench.empty:
                            if 'SPY' in df_bench.columns: bench_cols.append('SPY'); rename_map['SPY'] = 'S&P 500'
                            if 'URTH' in df_bench.columns: bench_cols.append('URTH'); rename_map['URTH'] = 'MSCI World'
                            elif 'MSCI' in df_bench.columns: bench_cols.append('MSCI'); rename_map['MSCI'] = 'MSCI World'

                        df_b_sub = df_bench[['Date'] + bench_cols].copy() if not df_bench.empty else pd.DataFrame(columns=['Date']); df_b_sub['Date'] = pd.to_datetime(df_b_sub['Date'])
                        latest_d = df_prices['Date'].max()
                        st.markdown("---"); st.subheader(f"Crowded Index Performance (as of {latest_d.strftime('%Y-%m-%d')})")

                        plot_df = pd.DataFrame()
                        if not df_crowded_shadow.empty:
                            plot_df['Date'] = pd.to_datetime(df_crowded_shadow['Date'])
                            plot_df['Crowded Index'] = (df_crowded_shadow['Actual %'] / 100) + 1
                            plot_df['Crowded Index (Shadow)'] = (df_crowded_shadow['Shadow %'] / 100) + 1
                        else:
                             plot_df['Date'] = pd.to_datetime(df_crowded_cum['Date'])
                             plot_df['Crowded Index'] = df_crowded_cum['Cum_Ret']

                        table_df = pd.merge_asof(plot_df.sort_values('Date'), df_b_sub.sort_values('Date'), on='Date', direction='nearest').dropna()

                        plot_merged = table_df.copy()
                        main_assets = [c for c in ['Crowded Index', 'Crowded Index (Shadow)'] if c in plot_merged.columns]

                        if not plot_merged.empty:
                            for c in main_assets + bench_cols: plot_merged[c] = (plot_merged[c] / plot_merged[c].iloc[0]) * 100

                            plot_vars = main_assets + bench_cols
                            melt_plot = plot_merged.melt(id_vars=['Date'], value_vars=plot_vars, var_name='Strategy', value_name='Indexed (Base 100)')
                            melt_plot['Strategy'] = melt_plot['Strategy'].map(lambda x: rename_map.get(x, x))

                            fig = px.line(melt_plot, x='Date', y='Indexed (Base 100)', color='Strategy', template=chart_template)
                            st.plotly_chart(fig, use_container_width=True)

                            generate_performance_tables(table_df, main_assets, bench_cols, rename_map, latest_date_override=latest_d)

                        st.markdown("---")
                        with st.expander("View Quarterly Crowded Index Constituents"):
                            if top_5_crowded_quarterly:
                                df_constituents = pd.DataFrame(top_5_crowded_quarterly)
                                df_constituents['report_date'] = pd.to_datetime(df_constituents['report_date']).dt.strftime('%Y-%m-%d')
                                st.dataframe(df_constituents[['report_date', 'top_5_display']].set_index('report_date').rename(columns={'top_5_display': 'Top 5 Securities'}), use_container_width=True)
                            else:
                                st.write("No constituents data to display.")
