import streamlit as st
import pandas as pd
import plotly.express as px

def render(df_filtered, df_raw, ticker_to_name, selected_funds, chart_template, df_funds=pd.DataFrame()):
    st.subheader("Single Manager Tear Sheet")
    funds = sorted(df_filtered['fund_name'].unique())
    
    if not funds:
        st.warning("No funds selected.")
        return
        
    col_m1, col_m2, col_m3 = st.columns(3)
    with col_m1:
        sel_mgr = st.selectbox("Select Manager:", funds, key="tab3_mgr")

    with col_m3:
        st.write("") # Vertical spacing
        exclude_synthetic = st.toggle("Exclude Synthetic Prices", key="tab3_exclude")

    # Filter manager data based on the toggle BEFORE determining available quarters
    df_mgr_base = df_filtered[df_filtered['fund_name'] == sel_mgr].copy()
    if exclude_synthetic:
        df_mgr_all = df_mgr_base[~df_mgr_base['ticker'].str.startswith('SYN_')].copy()
    else:
        df_mgr_all = df_mgr_base.copy()
    
    # Filter for Equity Only for the main dashboard logic
    df_mgr = df_mgr_all[df_mgr_all['put_call'] == 'SHARE'].copy()
    
    # Recalculate weights so they sum to 100% of the Equity Portfolio (excluding options from the denominator)
    df_mgr['Concentration %'] = df_mgr.groupby('report_date')['standardized_market_value'].transform(lambda x: (x / x.sum()) * 100)

    mgr_qtrs = sorted(df_mgr['report_date'].unique(), reverse=True)
    
    with col_m2:
        if not mgr_qtrs:
            st.warning("No equity data for manager with current filters.")
            return
        mgr_qtr_str = st.selectbox("Select Quarter:", [d.strftime('%Y-%m-%d') for d in mgr_qtrs])
        
    mgr_qtr = pd.to_datetime(mgr_qtr_str)
    df_mgr_curr = df_mgr[df_mgr['report_date'] == mgr_qtr]
    
    # We need the full dataset (including options) for the specific options chart
    df_mgr_curr_all = df_mgr_all[df_mgr_all['report_date'] == mgr_qtr]
    
    prev_mgr_qtrs = [q for q in mgr_qtrs if q < mgr_qtr]
    df_mgr_prev = df_mgr[df_mgr['report_date'] == prev_mgr_qtrs[0]] if prev_mgr_qtrs else pd.DataFrame()

    # --- A. Portfolio Overview (Pie Charts) ---
    st.markdown("---")
    st.markdown(f"### Portfolio Composition ({mgr_qtr.strftime('%Y-%m-%d')})")
    
    # Calculate and display 13F AUM for the selected quarter
    aum_13f = df_mgr_curr['standardized_market_value'].sum()
    if aum_13f > 0:
        st.markdown(f"**Total 13F Assets:** `${aum_13f / 1_000_000_000:.1f}B`")

    pc1, pc2, pc3 = st.columns(3)
    with pc1:
        st.markdown("###### Allocation by Stock")
        fig_pie_stock = px.pie(df_mgr_curr, values='standardized_market_value', names='ticker', 
                               template=chart_template)
        fig_pie_stock.update_traces(textposition='inside', textinfo='percent+label')
        fig_pie_stock.update_layout(height=450, title_text=" ")
        st.plotly_chart(fig_pie_stock, use_container_width=True)
        
    with pc2:
        st.markdown("###### Allocation by Sector")
        fig_pie_sec = px.pie(df_mgr_curr, values='standardized_market_value', names='sector', 
                             template=chart_template)
        fig_pie_sec.update_layout(height=450, title_text=" ")
        st.plotly_chart(fig_pie_sec, use_container_width=True)

    with pc3:
        st.markdown("###### Allocation by Option Underlying")
        df_options = df_mgr_curr_all[df_mgr_curr_all['put_call'].isin(['Put', 'Call'])].copy()

        if not df_options.empty:
            # Calculate total option value
            total_option_value = df_options['standardized_market_value'].sum()
            formatted_total_value = f"${total_option_value / 1_000_000:.0f}M"
            
            # Create a new column for the legend
            df_options['legend_label'] = df_options['put_call'] + ': ' + df_options['ticker']

            fig_pie_options = px.pie(
                df_options, 
                values='standardized_market_value', 
                names='legend_label',
                template=chart_template,
                color='put_call',
                color_discrete_map={'Call': 'red', 'Put': 'blue'},
                hole=0.4 # Make it a doughnut chart
            )
            
            fig_pie_options.update_traces(
                textposition='inside', 
                textinfo='percent',
                hovertemplate='%{label}<br>Market Value: $%{value:,.2f}<extra></extra>'
            )
            fig_pie_options.update_layout(
                height=450,
                showlegend=True,
                title_text=" ", # Clear the default title
                annotations=[dict(text=formatted_total_value, x=0.5, y=0.5, font_size=20, showarrow=False)]
            )
            st.plotly_chart(fig_pie_options, use_container_width=True)
            st.caption("Option Value = (Number of Option Contracts) × (Multiplier) × (Closing Price of the Underlying Stock)")
        else:
            st.info("No option positions held in this quarter.")


    # --- B. Portfolio Changes ---
    st.markdown("---")
    st.markdown("### Quarterly Shifts (vs Previous Quarter)")
    
    if df_mgr_prev.empty:
        st.info("No previous quarter data available to calculate shifts.")
    else:
        curr_weights = df_mgr_curr.set_index('ticker')['Concentration %']
        prev_weights = df_mgr_prev.set_index('ticker')['Concentration %']
        
        changes = curr_weights.subtract(prev_weights, fill_value=0).reset_index()
        changes.columns = ['Ticker', 'Delta Weight %']
        changes['Company'] = changes['Ticker'].map(ticker_to_name)
        
        new_tickers = set(df_mgr_curr['ticker']) - set(df_mgr_prev['ticker'])
        exited_tickers = set(df_mgr_prev['ticker']) - set(df_mgr_curr['ticker'])
        
        chg_up = changes[(changes['Delta Weight %'] > 0) & (~changes['Ticker'].isin(new_tickers))].sort_values('Delta Weight %', ascending=False).head(5)
        chg_down = changes[(changes['Delta Weight %'] < 0) & (~changes['Ticker'].isin(exited_tickers))].sort_values('Delta Weight %', ascending=True).head(5)
        
        new_pos_df = df_mgr_curr[df_mgr_curr['ticker'].isin(new_tickers)][['name_of_issuer', 'ticker', 'Concentration %']].sort_values('Concentration %', ascending=False).head(5)
        exited_pos_df = df_mgr_prev[df_mgr_prev['ticker'].isin(exited_tickers)][['name_of_issuer', 'ticker', 'Concentration %']].sort_values('Concentration %', ascending=False).head(5)

        col_u1, col_u2, col_u3, col_u4 = st.columns(4)
        
        with col_u1:
            st.markdown("**Top Position Increases**")
            if not chg_up.empty:
                chg_up['Delta Weight %'] = chg_up['Delta Weight %'].map('+{:.2f}%'.format)
                st.dataframe(chg_up[['Company', 'Ticker', 'Delta Weight %']].set_index('Ticker'), width='stretch')
            else: st.write("None")
                
        with col_u2:
            st.markdown("**Top Position Decreases**")
            if not chg_down.empty:
                chg_down['Delta Weight %'] = chg_down['Delta Weight %'].map('{:.2f}%'.format)
                st.dataframe(chg_down[['Company', 'Ticker', 'Delta Weight %']].set_index('Ticker'), width='stretch')
            else: st.write("None")
                
        with col_u3:
            st.markdown("**Top New Positions**")
            if not new_pos_df.empty:
                new_pos_df.columns = ['Company', 'Ticker', 'New Weight %']
                new_pos_df['New Weight %'] = new_pos_df['New Weight %'].map('{:.2f}%'.format)
                st.dataframe(new_pos_df.set_index('Ticker'), width='stretch')
            else: st.write("None")
                
        with col_u4:
            st.markdown("**Top Exited Positions**")
            if not exited_pos_df.empty:
                exited_pos_df.columns = ['Company', 'Ticker', 'Prev Weight %']
                exited_pos_df['Prev Weight %'] = exited_pos_df['Prev Weight %'].map('{:.2f}%'.format)
                st.dataframe(exited_pos_df.set_index('Ticker'), width='stretch')
            else: st.write("None")

    # --- D. Fund Overlap Matrix (Value-Based Algorithm) ---
    st.markdown("---")
    st.markdown(f"### Top Fund Overlap Matrix ({mgr_qtr.strftime('%Y-%m-%d')})")
    st.write("Percentage of a peer fund's total portfolio value is made up of stocks currently held by the selected manager.")
    
    # Filter peers for Equity Only to ensure apples-to-apples comparison
    df_all_curr = df_raw[(df_raw['report_date'] == mgr_qtr) & (df_raw['put_call'] == 'SHARE')].copy()
    mgr_ticker_set = set(df_mgr_curr['ticker'])
    
    overlap_data = []
    for other_fund in df_all_curr['fund_name'].unique():
        if other_fund == sel_mgr: continue
        
        peer_df = df_all_curr[df_all_curr['fund_name'] == other_fund]
        peer_total_val = peer_df['standardized_market_value'].sum()
        
        if peer_total_val <= 0: continue
        
        shared_df = peer_df[peer_df['ticker'].isin(mgr_ticker_set)]
        shared_val = shared_df['standardized_market_value'].sum()
        
        overlap_pct = (shared_val / peer_total_val) * 100
        
        if overlap_pct > 0:
            overlap_data.append({
                'Peer Fund': other_fund, 
                'Shared Tickers': len(shared_df), 
                'Peer Portfolio Overlap (%)': overlap_pct
            })
        
    if overlap_data:
        overlap_df = pd.DataFrame(overlap_data).sort_values('Peer Portfolio Overlap (%)', ascending=False).head(5)
        overlap_df['Peer Portfolio Overlap (%)'] = overlap_df['Peer Portfolio Overlap (%)'].map('{:.1f}%'.format)
        st.dataframe(overlap_df.set_index('Peer Fund'), width='stretch')
    else:
        st.info("No overlapping positions found with other funds in the database for this quarter.")

    # --- C. Holding Analysis ---
    st.markdown("---")
    
    hc_title, hc_btn = st.columns([3, 1])
    with hc_title:
        st.markdown("### Holding Period Analytics (All Time)")
    with hc_btn:
        st.write("") # Alignment
        univ_df = df_filtered[(df_filtered['fund_name'] == sel_mgr) & (df_filtered['put_call'] == 'SHARE')]
        exp_cols = ['ticker', 'cusip', 'name_of_issuer'] if 'cusip' in univ_df.columns else ['ticker', 'name_of_issuer']
        csv_data = univ_df[exp_cols].drop_duplicates().sort_values('ticker').to_csv(index=False).encode('utf-8')
        st.download_button(label="💾 Download Universe (ITD)", data=csv_data, file_name=f"{sel_mgr}_universe_itd.csv", mime="text/csv")
    
    # Use the equity-only dataset for holding period analysis
    df_history_up_to_qtr = df_mgr[df_mgr['report_date'] <= mgr_qtr]
    
    if not df_history_up_to_qtr.empty:
        hold_stats = df_history_up_to_qtr.groupby('ticker').agg(
            Company=('name_of_issuer', 'first'),
            Qtrs_Held=('report_date', 'nunique'),
            Last_Qtr=('report_date', 'max')
        ).reset_index()
        
        hold_stats['Status'] = hold_stats['Last_Qtr'].apply(lambda x: 'Open' if x == mgr_qtr else 'Closed')
        
        st.write(f"Distribution of holding periods for all {len(hold_stats)} stocks the fund has ever held (up to selected quarter):")
        fig_mgr_bx = px.box(hold_stats, y='Qtrs_Held', color='Status', points="all", hover_data=['Company', 'ticker'],
                            title=f"{sel_mgr}: Holding Period Distribution (All Time)", template=chart_template)
        fig_mgr_bx.update_layout(yaxis_title="Number of Quarters Held")
        st.plotly_chart(fig_mgr_bx, width='stretch')
        
        longest = hold_stats.sort_values('Qtrs_Held', ascending=False).head(5)
        shortest = hold_stats.sort_values('Qtrs_Held', ascending=True).head(5)
        
        hc1, hc2 = st.columns(2)
        with hc1:
            st.markdown("**Longest Held Positions (Quarters)**")
            st.dataframe(longest.set_index('ticker')[['Company', 'Qtrs_Held', 'Status']], width='stretch')
        with hc2:
            st.markdown("**Shortest Held Positions (Quarters)**")
            st.dataframe(shortest.set_index('ticker')[['Company', 'Qtrs_Held', 'Status']], width='stretch')
    else:
        st.info("No historical data available for the selected manager and quarter.")