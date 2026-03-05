import requests
import pandas as pd
from bs4 import BeautifulSoup
import time # Added to prevent SEC IP bans

def get_historical_13f_urls(cik, years_back=10):
    """
    Searches SEC EDGAR and returns a list of URLs for a fund's 13F-HR XML files 
    going back a specified number of years.
    """
    padded_cik = str(cik).zfill(10)
    headers = {'User-Agent': 'Jakob HedgeFundTracker Project (jakobsinvestmentnewsletter@gmail.com)'}
    
    submissions_url = f"https://data.sec.gov/submissions/CIK{padded_cik}.json"
    response = requests.get(submissions_url, headers=headers)
    
    if response.status_code != 200:
        print(f"Failed to fetch filing history for CIK {cik}")
        return []

    data = response.json()
    df_filings = pd.DataFrame(data['filings']['recent'])
    
    # Filter for 13F-HR
    df_13f = df_filings[df_filings['form'] == '13F-HR'].reset_index(drop=True)
    
    # Calculate how many quarters to grab (4 quarters * years_back)
    quarters_to_fetch = years_back * 4
    df_13f = df_13f.head(quarters_to_fetch)
    
    if df_13f.empty:
        print(f"No 13F-HR found for CIK {cik}")
        return []

    archive_cik = str(int(cik))
    historical_filings = []

    print(f"    Found {len(df_13f)} historical filings. Hunting for XML files...")
    
    # Loop through the history
    for index, row in df_13f.iterrows():
        accession_no_dashes = row['accessionNumber'].replace('-', '')
        report_date = row['reportDate']
        
        index_url = f"https://www.sec.gov/Archives/edgar/data/{archive_cik}/{accession_no_dashes}/index.json"
        
        # Pause for 0.15 seconds to respect SEC rate limits (10 requests/sec limit)
        time.sleep(0.15)
        
        index_response = requests.get(index_url, headers=headers)
        if index_response.status_code != 200:
            continue
            
        directory_data = index_response.json()
        xml_filename = None
        
        # Find the XML file
        for file in directory_data['directory']['item']:
            name = file['name']
            if name.endswith('.xml') and ('info' in name.lower() or 'table' in name.lower()):
                xml_filename = name
                break
                
        if not xml_filename:
            for file in directory_data['directory']['item']:
                if file['name'].endswith('.xml') and 'primary' not in file['name'].lower():
                    xml_filename = file['name']
                    break

        if xml_filename:
            final_xml_url = f"https://www.sec.gov/Archives/edgar/data/{archive_cik}/{accession_no_dashes}/{xml_filename}"
            historical_filings.append((final_xml_url, report_date))

    return historical_filings


def parse_and_standardize_13f(xml_url, fund_name, report_date):
    """
    Downloads the XML, extracts the holdings, and automatically corrects 
    the SEC reporting glitch where some funds report in $1,000s instead of exact dollars.
    """
    headers = {'User-Agent': 'Jakob HedgeFundTracker Project (jakobsinvestmentnewsletter@gmail.com)'}
    
    # Pause again before downloading the actual massive XML file
    time.sleep(0.15)
    response = requests.get(xml_url, headers=headers)
    
    if response.status_code != 200:
        return None

    soup = BeautifulSoup(response.content, 'xml')
    holdings = soup.find_all('infoTable')
    parsed_data = []
    
    for holding in holdings:
        def get_text(tag_name):
            tag = holding.find(tag_name)
            return tag.text.strip() if tag else None

        name = get_text('nameOfIssuer')
        title = get_text('titleOfClass')
        cusip = get_text('cusip')
        
        raw_value = get_text('value')
        reported_value = float(raw_value) if raw_value else 0.0
        
        shrs_tag = holding.find('shrsOrPrnAmt')
        shares = float(shrs_tag.find('sshPrnamt').text) if shrs_tag else 0.0
        put_call = get_text('putCall')

        parsed_data.append({
            'fund_name': fund_name,
            'report_date': report_date,
            'name_of_issuer': name,
            'title_of_class': title,
            'cusip': cusip,
            'reported_value': reported_value,
            'shares': shares,
            'put_call': put_call
        })
        
    df = pd.DataFrame(parsed_data)
    
    if df.empty:
        return df
        
    # --- Auto-Correct Logic for $1,000s vs Exact Dollars ---
    equity_only = df[df['put_call'].isna() & (df['shares'] > 0)]
    
    if not equity_only.empty:
        implied_prices = equity_only['reported_value'] / equity_only['shares']
        median_implied_price = implied_prices.median()
        
        if median_implied_price < 1.0:
            df['standardized_market_value'] = df['reported_value'] * 1000
        else:
            df['standardized_market_value'] = df['reported_value']
    else:
        df['standardized_market_value'] = df['reported_value']

    return df