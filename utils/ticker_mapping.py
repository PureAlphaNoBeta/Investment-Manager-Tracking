import requests
import pandas as pd
import time

def map_cusips_to_tickers(df_holdings, api_key=None):
    """
    Takes a dataframe of holdings, extracts unique CUSIPs/CINS, and queries OpenFIGI.
    Automatically detects foreign CINS codes (like Spotify) vs US CUSIPs.
    """
    print("  -> Mapping Identifiers to Tickers via OpenFIGI (with CINS support)...")
    
    unique_cusips = df_holdings['cusip'].dropna().unique().tolist()
    print(f"     Found {len(unique_cusips)} unique identifiers to translate.")
    
    headers = {'Content-Type': 'application/json'}
    if api_key:
        headers['X-OPENFIGI-APIKEY'] = api_key

    batch_size = 100 if api_key else 10
    mapping_dict = {}

    for i in range(0, len(unique_cusips), batch_size):
        batch = unique_cusips[i:i + batch_size]
        
        payload = []
        for cusip in batch:
            # THE SMART DETECTION: If it starts with a letter, it is a foreign CINS
            if str(cusip)[0].isalpha():
                payload.append({"idType": "ID_CINS", "idValue": cusip, "exchCode": "US"})
            else:
                # Otherwise, it is a standard US CUSIP
                payload.append({"idType": "ID_CUSIP", "idValue": cusip, "exchCode": "US"})
        
        response = requests.post('https://api.openfigi.com/v3/mapping', headers=headers, json=payload)
        
        if response.status_code == 200:
            results = response.json()
            for j, result in enumerate(results):
                cusip = batch[j]
                if 'data' in result and len(result['data']) > 0:
                    # Grab the standard ticker symbol
                    mapping_dict[cusip] = result['data'][0].get('ticker', 'UNKNOWN')
                else:
                    mapping_dict[cusip] = 'UNKNOWN'
        elif response.status_code == 429:
            print("     [!] Rate limit hit. Waiting 10 seconds...")
            time.sleep(10)
        else:
            print(f"     [!] API Error {response.status_code}: {response.text}")

        time.sleep(1 if api_key else 3)
        
    df_holdings['ticker'] = df_holdings['cusip'].map(mapping_dict)
    df_holdings['ticker'] = df_holdings['ticker'].fillna('UNKNOWN')
    
    mapped_count = len([v for v in mapping_dict.values() if v != 'UNKNOWN'])
    print(f"  -> Successfully mapped {mapped_count} out of {len(unique_cusips)} identifiers.")
    
    return df_holdings