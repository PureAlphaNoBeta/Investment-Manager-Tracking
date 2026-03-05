import streamlit as st
import pandas as pd
import plotly.express as px
import numpy as np

def render(df_raw, df_funds, selected_funds):
    st.subheader("🗺️ Office Map")

    # --- 1. Data Validation ---
    if df_funds.empty or 'address_city' not in df_funds.columns or 'lat' not in df_funds.columns:
        st.warning("⚠️ Fund address data is missing or out of date. Please run the fund address update script first.")
        return

    mappable_funds = df_funds[df_funds['address_city'].notna() & (df_funds['address_city'] != '')].copy()
    if mappable_funds.empty:
        st.warning("No funds have valid city data.")
        return
    
    # --- 2. Manager/City Selection ---
    available_funds = sorted(mappable_funds['fund_name'].unique())
    available_cities = sorted(list(set([str(c).title() for c in mappable_funds['address_city'].unique() if pd.notna(c) and c != ''])))

    col_toggle1, col_toggle2 = st.columns([1, 2])
    with col_toggle1:
        view_mode = st.radio("Select View Mode:", ["By Manager", "By City"], horizontal=True)

    col1, col2 = st.columns([1, 2])
    
    if view_mode == "By Manager":
        with col1:
            sel_mgr = st.selectbox("Select Manager to Map:", available_funds, key="tab5_mgr_select")
            if not sel_mgr:
                return

        mgr_info = mappable_funds[mappable_funds['fund_name'] == sel_mgr].iloc[0]
        sel_city = str(mgr_info['address_city']).title()
        sel_state = mgr_info.get('address_state', '')
        
        st.info(f"📍 Analyzing **{sel_mgr}** and peers in **{sel_city}, {sel_state}**")

        # Focus funds: the manager and peers in the same city
        city_peers_df = mappable_funds[
            (mappable_funds['address_city'].str.lower() == str(sel_city).lower()) & 
            (mappable_funds['address_state'].str.lower() == str(sel_state).lower()) & 
            (mappable_funds['fund_name'] != sel_mgr)
        ]
        
        # Calculate Overlap Logic
        latest_date = df_raw['report_date'].max()
        df_latest = df_raw[(df_raw['report_date'] == latest_date) & (df_raw['put_call'] == 'SHARE')]
        mgr_holdings = df_latest[df_latest['fund_name'] == sel_mgr]
        mgr_tickers = set(mgr_holdings['ticker'])
        
        overlap_results = []
        for peer in city_peers_df['fund_name'].unique():
            peer_holdings = df_latest[df_latest['fund_name'] == peer]
            peer_total_val = peer_holdings['standardized_market_value'].sum()
            if peer_total_val > 0:
                shared_val = peer_holdings[peer_holdings['ticker'].isin(mgr_tickers)]['standardized_market_value'].sum()
                overlap_results.append({'fund_name': peer, 'overlap_pct': (shared_val / peer_total_val) * 100})
        
        df_overlap = pd.DataFrame(overlap_results)
        
        if not df_overlap.empty:
            df_overlap = df_overlap.sort_values('overlap_pct', ascending=False).head(10)
            top_peer_names = df_overlap['fund_name'].tolist()
        else:
            top_peer_names = []

        df_map = mappable_funds[mappable_funds['fund_name'].isin([sel_mgr] + top_peer_names)].copy()
        if not df_overlap.empty:
            df_map = pd.merge(df_map, df_overlap, on='fund_name', how='left')
        else:
            df_map['overlap_pct'] = 0.0
        df_map['overlap_pct'] = df_map['overlap_pct'].fillna(100.0) # self overlap
        df_map['Marker_Type'] = df_map['fund_name'].apply(lambda x: 'Target Manager' if x == sel_mgr else 'Peer')
        
    else: # By City mode
        with col1:
            sel_city = st.selectbox("Select City to Map:", available_cities, key="tab5_city_select")
            if not sel_city:
                return
                
        # Find all funds in this city
        df_map = mappable_funds[mappable_funds['address_city'].str.lower() == str(sel_city).lower()].copy()
        
        # In city mode, we don't have a single "Target Manager" to calculate overlap against,
        # so we set default values for map compatibility
        df_map['overlap_pct'] = 0.0 
        df_map['Marker_Type'] = 'Fund in City'
        
        states = df_map['address_state'].unique()
        state_str = ", ".join([str(s) for s in states if pd.notna(s)])
        st.info(f"📍 Showing all **{len(df_map)}** funds located in **{sel_city}{', ' + state_str if state_str else ''}**")


    # --- 3. Coordinate Jittering ---
    # Jitter coordinates that are not an exact match to prevent them overlapping identically on map
    if 'match_quality' in df_map.columns:
        mask = df_map['match_quality'] != "Exact Match"
        if mask.any():
            df_map.loc[mask, 'lat'] += np.random.uniform(-0.0012, 0.0012, mask.sum())
            df_map.loc[mask, 'lon'] += np.random.uniform(-0.0012, 0.0012, mask.sum())
    
    # Ensure backwards compatibility if fields are missing for a fund
    if 'formatted_address' not in df_map.columns:
        df_map['formatted_address'] = df_map.apply(lambda row: f"{row.get('address_street1', '')} {row.get('address_city', '')} {row.get('address_state', '')}", axis=1)
    if 'match_quality' not in df_map.columns:
        df_map['match_quality'] = 'Unknown'

    # --- 4. Map Visualization (Uniform Marker Sizes) ---
    plot_df = df_map.dropna(subset=['lat'])
    
    if not plot_df.empty:
        # Dynamic color mapping based on view mode
        if view_mode == "By Manager":
            color_map = {'Target Manager': '#FF4B4B', 'Peer': '#0068C9'}
            hover_dict = {"formatted_address": True, "match_quality": True, "overlap_pct": ":.1f", "lat": False, "lon": False, "Marker_Type": False}
        else:
            color_map = {'Fund in City': '#0068C9'}
            hover_dict = {"formatted_address": True, "match_quality": True, "lat": False, "lon": False, "Marker_Type": False, "overlap_pct": False}
            
        fig = px.scatter_mapbox(
            plot_df, lat="lat", lon="lon", 
            color="Marker_Type", 
            hover_name="fund_name",
            hover_data=hover_dict,
            color_discrete_map=color_map,
            zoom=12, height=600
        )
        
        fig.update_traces(marker=dict(size=15))
        fig.update_layout(mapbox_style="open-street-map", margin={"r":0,"t":0,"l":0,"b":0})
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("Could not find coordinates for these locations to display on the map.")

    # --- 5. Data Table with Conditional Formatting ---
    st.markdown("### 🏢 Location Details")
    
    def style_table(row):
        styles = [''] * len(row)
        if row['Quality'] != 'Exact Match':
            styles = ['background-color: rgba(255, 165, 0, 0.15)'] * len(row)
        if view_mode == "By Manager" and row['Fund Name'] == sel_mgr:
            styles = [s + '; font-weight: bold;' for s in styles]
        return styles

    if view_mode == "By Manager":
        cols_to_keep = ['fund_name', 'formatted_address', 'overlap_pct', 'match_quality']
        target_df = df_map[df_map['fund_name'] == sel_mgr][cols_to_keep].copy()
        peers_df = df_map[df_map['fund_name'] != sel_mgr][cols_to_keep].copy()
        peers_df = peers_df.sort_values('overlap_pct', ascending=False)
        table_df = pd.concat([target_df, peers_df])
        table_df.columns = ['Fund Name', 'Interpreted Address', 'Overlap %', 'Quality']
        
        if not table_df.empty:
            st.dataframe(
                table_df.style.format({'Overlap %': '{:.1f}%'}).apply(style_table, axis=1),
                use_container_width=True
            )
    else:
        # City Mode table
        cols_to_keep = ['fund_name', 'formatted_address', 'match_quality']
        table_df = df_map[cols_to_keep].copy().sort_values('fund_name')
        table_df.columns = ['Fund Name', 'Interpreted Address', 'Quality']
        
        if not table_df.empty:
            st.dataframe(
                table_df.style.apply(style_table, axis=1),
                use_container_width=True
            )

    if not table_df.empty and (table_df['Quality'] != 'Exact Match').any():
        st.caption("⚠️ **Note:** Rows highlighted in orange have unrecognized or messy street addresses and are placed at the city or general street level.")