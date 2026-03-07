import sqlite3
import pandas as pd
import requests
import time
import os
import phonenumbers
import re  
from geopy.geocoders import Nominatim

# Configuration
DB_PATH = os.path.join("data", "hedge_funds.db")
USER_AGENT = 'Jakob HedgeFundTracker Project (jakobsinvestmentnewsletter@gmail.com)'

# Initialize Geolocator
geolocator = Nominatim(user_agent="fund_explorer_v5_pro")

def format_phone_number(raw_phone, state, city, zip_code):
    if not raw_phone:
        return raw_phone
        
    raw_phone = str(raw_phone).strip()
    
    if raw_phone.startswith('+'):
        try:
            parsed = phonenumbers.parse(raw_phone, None)
            if phonenumbers.is_valid_number(parsed):
                return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.INTERNATIONAL)
        except phonenumbers.phonenumberutil.NumberParseException:
            pass

    us_states = {
        "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", 
        "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD", 
        "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ", 
        "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC", 
        "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
        "DC", "PR", "VI"
    }

    hub_regions = {
        "LONDON": "GB", "HONG KONG": "HK", "SINGAPORE": "SG", "TOKYO": "JP",
        "GENEVA": "CH", "ZURICH": "CH", "DUBAI": "AE", "PARIS": "FR",
        "TORONTO": "CA", "MONTREAL": "CA", "CALGARY": "CA",
        "GEORGE TOWN": "KY", "GRAND CAYMAN": "KY", "CAMANA BAY": "KY",
        "HAMILTON": "BM", "ST. HELIER": "JE", "ROAD TOWN": "VG"
    }
    
    region_guess = str(state).upper() if state else ""
    city_upper = str(city).upper() if city else ""
    
    if region_guess in us_states:
        best_region = "US"
    elif region_guess in phonenumbers.SUPPORTED_REGIONS:
        best_region = region_guess
    elif city_upper in hub_regions:
        best_region = hub_regions[city_upper]
    else:
        best_region = "US"
        
    try:
        parsed = phonenumbers.parse(raw_phone, best_region)
        if phonenumbers.is_valid_number(parsed):
            return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.INTERNATIONAL)
    except phonenumbers.phonenumberutil.NumberParseException:
        pass
        
    return raw_phone

def normalize_location(city, state):
    city_upper = str(city).upper().strip() if city else ""
    state_upper = str(state).upper().strip() if state else ""
    
    hubs = {
        "GEORGE TOWN": "Cayman Islands", "GRAND CAYMAN": "Cayman Islands", "CAMANA BAY": "Cayman Islands",
        "ROAD TOWN": "British Virgin Islands", "TORTOLA": "British Virgin Islands",
        "ST. HELIER": "Jersey", "ST HELIER": "Jersey",
        "ST. PETER PORT": "Guernsey", "ST PETER PORT": "Guernsey",
        "HONG KONG": "Hong Kong", "SINGAPORE": "Singapore", "TOKYO": "Japan",
        "DUBAI": "United Arab Emirates", "ZURICH": "Switzerland", "GENEVA": "Switzerland"
    }
    
    if city_upper in hubs:
        return hubs[city_upper]
        
    if city_upper == "LONDON" and state_upper not in ["OH", "KY", "ON", "ONTARIO"]:
        return "United Kingdom"
    if city_upper == "HAMILTON" and state_upper not in ["OH", "NJ", "MA", "ON", "ONTARIO"]:
        return "Bermuda"
    if city_upper == "PARIS" and state_upper not in ["TX", "TN", "KY"]:
        return "France"
        
    sec_codes = {
        "E9": "Cayman Islands", "X0": "United Kingdom", 
        "K3": "Hong Kong", "H2": "Hong Kong", 
        "Z4": "Switzerland", "F4": "Bermuda", "M3": "Japan"
    }
    if state_upper in sec_codes:
        return sec_codes[state_upper]
    
    return state

def clean_address_fields(street, city, state, zip_raw):
    street = str(street).strip() if street else ""
    city = str(city).strip() if city else ""
    state = str(state).strip() if state else ""
    zip_raw = str(zip_raw).strip() if zip_raw else ""

    if street.lower() in ['nan', 'null', 'none']: street = ""
    if city.lower() in ['nan', 'null', 'none']: city = ""
    if zip_raw.lower() in ['nan', 'null', 'none']: zip_raw = ""

    if state == "United Kingdom":
        uk_postcode_regex = r'^[A-Za-z]{1,2}\d[A-Za-z\d]?\s?\d[A-Za-z]{2}$'
        if re.match(uk_postcode_regex, street, re.IGNORECASE) or \
           (zip_raw and zip_raw[0].isdigit() and len(zip_raw) > 8 and street and street[0].isalpha() and len(street) <= 8):
            street, zip_raw = zip_raw, street

    if state == "Hong Kong" or zip_raw in ['00000', '999077']:
        zip_raw = ""

    return street, city, state, zip_raw

def clean_address_string(street_str):
    """Aggressively strip suite, floor, and building markers that break Nominatim."""
    if not street_str: return ""
    
    # Convert spelled out numbers at the start of the address
    word_to_num = {
        r'^ONE\b': '1', r'^TWO\b': '2', r'^THREE\b': '3', r'^FOUR\b': '4', 
        r'^FIVE\b': '5', r'^SIX\b': '6', r'^SEVEN\b': '7', r'^EIGHT\b': '8', r'^NINE\b': '9'
    }
    
    res = str(street_str).upper()
    for word, num in word_to_num.items():
        res = re.sub(word, num, res)
        
    # Expand common abbreviations that Nominatim hates
    res = re.sub(r'\bPLZ\b', 'PLAZA', res)
    res = re.sub(r'\bSTE\b', 'SUITE', res)
    res = re.sub(r'\bFL\b', 'FLOOR', res)
    res = re.sub(r'\bBLDG\b', 'BUILDING', res)
    res = re.sub(r'\bAPT\b', 'APARTMENT', res)

    # Remove c/o lines
    res = re.sub(r'^C/O\s+.*?,', '', res)
    
    # 1. Try stripping anything after a comma if the last part looks like a floor/suite
    parts = [p.strip() for p in res.split(',')]
    if len(parts) > 1:
        last_part = parts[-1]
        if any(keyword in last_part for keyword in ['FLOOR', 'SUITE', 'ROOM', 'UNIT', 'APARTMENT', 'BUILDING']):
            res = ', '.join(parts[:-1])

    # 2. Try removing trailing modifiers if there are no commas (e.g., "40 WEST 57TH STREET 18TH FLOOR")
    pattern = r'\b(\d+(?:ST|ND|RD|TH)?\s+(?:FLOOR)|SUITE\s+\w+|BUILDING\s+\w+|ROOM\s+\w+)\b'
    res = re.sub(pattern, '', res).strip(' ,')
    
    return res

def get_geocoding_candidates(street1, street2, city, state_or_country, zip_code):
    street1 = str(street1).strip() if street1 and not pd.isna(street1) else ""
    street2 = str(street2).strip() if street2 and not pd.isna(street2) else ""
    city = str(city).strip() if city and not pd.isna(city) else ""
    state_or_country = str(state_or_country).strip() if state_or_country and not pd.isna(state_or_country) else ""
    zip_code = str(zip_code).strip() if zip_code and not pd.isna(zip_code) else ""
    
    has_street1 = bool(street1)
    has_street2 = bool(street2)
    has_zip = bool(zip_code)
    
    addr_candidates = []
    
    clean_street1 = clean_address_string(street1) if has_street1 else ""
    clean_street2 = clean_address_string(street2) if has_street2 else ""
    has_clean1 = bool(clean_street1)
    has_clean2 = bool(clean_street2)
    
    # 1. Best attempt: Clean Street 1 + City + Zip + Country (Most accurate, avoids '6TH FLOOR' confusion)
    if has_clean1 and has_zip:
        cand = f"{clean_street1}, {city} {zip_code}, {state_or_country}".replace("  ", " ").replace(" ,", ",").strip(", ")
        if cand not in addr_candidates: addr_candidates.append(cand)
    
    # 2. Clean Street 1 + City + Country (Very accurate)
    if has_clean1:
        cand = f"{clean_street1}, {city}, {state_or_country}".replace("  ", " ").replace(" ,", ",").strip(", ")
        if cand not in addr_candidates: addr_candidates.append(cand)
        
    # 3. Clean Street 1 + Clean Street 2 + City + Country 
    if has_clean1 and has_clean2:
        combined_street = f"{clean_street1} {clean_street2}".strip()
        cand = f"{combined_street}, {city}, {state_or_country}".replace("  ", " ").replace(" ,", ",").strip(", ")
        if cand not in addr_candidates: addr_candidates.append(cand)
        
    # 4. Clean Street 2 + City + Country 
    if has_clean2:
        cand = f"{clean_street2}, {city}, {state_or_country}".replace("  ", " ").replace(" ,", ",").strip(", ")
        if cand not in addr_candidates: addr_candidates.append(cand)
        
    # 5. Raw Street 1 + Zip + Country (Fallback in case our cleaning broke something valid)
    if has_street1 and has_zip:
        cand = f"{street1}, {city} {zip_code}, {state_or_country}".replace("  ", " ").replace(" ,", ",").strip(", ")
        if cand not in addr_candidates: addr_candidates.append(cand)
        
    # 6. Raw Street 1 + Country
    if has_street1:
        cand = f"{street1}, {city}, {state_or_country}".replace("  ", " ").replace(" ,", ",").strip(", ")
        if cand not in addr_candidates: addr_candidates.append(cand)

    # 7. Street 1 stripped of all numbers + City + Country (General street level fallback)
    if has_clean1:
        street_no_num = "".join([i for i in clean_street1 if not i.isdigit()]).strip()
        if street_no_num:
            cand = f"{street_no_num}, {city}, {state_or_country}".replace("  ", " ").replace(" ,", ",").strip(", ")
            if cand not in addr_candidates: addr_candidates.append(cand)

    # 8. City and State (Lowest accuracy fallback)
    addr_city = f"{city}, {state_or_country}".replace(" ,", ",").strip(", ")
    if addr_city not in addr_candidates: addr_candidates.append(addr_city)
    
    display_street = " ".join(filter(None, [street1, street2]))
    addr_full = f"{display_street}, {city} {zip_code}, {state_or_country}".replace("  ", " ").replace(" ,", ",").strip(", ")
    
    return addr_full, addr_candidates

def geocode_address(street1, street2, city, state, zip_code):
    addr_full, candidates = get_geocoding_candidates(street1, street2, city, state, zip_code)
    
    lat, lon, m_type = None, None, "Failed"
    
    for idx, cand in enumerate(candidates):
        try:
            loc = geolocator.geocode(cand, timeout=5)
            # Mandatory Nominatim rate limit pause after EVERY request
            time.sleep(1.2)
            
            if loc:
                lat, lon = loc.latitude, loc.longitude
                
                # If we're on the very last candidate, it's just the city.
                if idx == len(candidates) - 1:
                    m_type = "City Level"
                else:
                    # Anything before the 'no numbers' string is an Exact Match
                    clean_s1 = clean_address_string(street1)
                    street_no_num = "".join([i for i in str(clean_s1).strip() if not i.isdigit()]).strip()
                    stripped_cand = f"{street_no_num}, {str(city).strip()}, {str(state).strip()}".replace("  ", " ").replace(" ,", ",").strip(", ")
                    
                    if cand == stripped_cand:
                        m_type = "Street Level"
                    else:
                        m_type = "Exact Match"
                break
        except Exception as e:
            # If we hit an exception (e.g., Timeout or 429 Too Many Requests), sleep longer
            time.sleep(2.0)
            
    return addr_full, lat, lon, m_type

def get_sec_data_and_geocode(cik):
    padded_cik = str(cik).zfill(10)
    url = f"https://data.sec.gov/submissions/CIK{padded_cik}.json"
    headers = {'User-Agent': USER_AGENT}
    
    try:
        time.sleep(0.12)
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            addresses = data.get('addresses', {})
            addr_obj = addresses.get('business') or addresses.get('mailing') or {}
            
            street1 = addr_obj.get('street1')
            city = addr_obj.get('city')
            state_or_country = addr_obj.get('stateOrCountry')
            zip_code = addr_obj.get('zipCode')
            raw_phone = data.get('phone')
            
            state_or_country = normalize_location(city, state_or_country)
            street1, city, state_or_country, zip_code = clean_address_fields(street1, city, state_or_country, zip_code)
            street2 = addr_obj.get('street2')
            
            as_of_date = None
            filings = data.get('filings', {}).get('recent', {})
            filing_dates = filings.get('filingDate', [])
            if filing_dates:
                as_of_date = filing_dates[0]
                
            formatted_addr, lat, lon, match_type = geocode_address(street1, street2, city, state_or_country, zip_code)
            
            basic_info = {
                'street1': street1,
                'street2': street2,
                'city': city,
                'state': state_or_country,
                'zip': zip_code,
                'phone': format_phone_number(raw_phone, state_or_country, city, zip_code), 
                'as_of': as_of_date,
                'formatted_address': formatted_addr,
                'lat': lat,
                'lon': lon,
                'match_quality': match_type
            }
            
            return basic_info
            
        elif response.status_code == 404:
            print(f"    ❌ CIK {cik} not found.")
            return None
        else:
            print(f"    ⚠️ SEC API Error: {response.status_code}")
            return None
            
    except Exception as e:
        print(f"    ❌ Exception for CIK {cik}: {e}")
        return None

def add_columns(cursor):
    columns_to_check = [
        ("address_street1", "TEXT"), ("address_street2", "TEXT"),
        ("address_city", "TEXT"), ("address_state", "TEXT"),
        ("address_zip", "TEXT"), ("phone", "TEXT"),
        ("address_as_of_date", "TEXT"), ("key_employees", "TEXT"), 
        ("filing_url_used", "TEXT"), ("formatted_address", "TEXT"),
        ("lat", "REAL"), ("lon", "REAL"), ("match_quality", "TEXT")
    ]
    cursor.execute("PRAGMA table_info(funds)")
    existing_columns = [row[1] for row in cursor.fetchall()]
    
    for col_name, col_type in columns_to_check:
        if col_name not in existing_columns:
            print(f"  -> Adding missing column '{col_name}'...")
            try:
                cursor.execute(f"ALTER TABLE funds ADD COLUMN {col_name} {col_type}")
            except sqlite3.OperationalError as e:
                print(f"    Warning: Could not add {col_name}: {e}")

def update_funds_table():
    if not os.path.exists(DB_PATH):
        print(f"❌ Database not found at: {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    add_columns(cursor)
    
    try:
        df_funds = pd.read_sql("SELECT fund_name, cik FROM funds", conn)
    except Exception as e:
        print(f"❌ Error reading table: {e}")
        conn.close()
        return

    print(f"🔍 Processing {len(df_funds)} funds...")
    updates = []
    
    for index, row in df_funds.iterrows():
        fund_name, cik = row['fund_name'], row['cik']
        print(f"  [{index + 1}/{len(df_funds)}] {fund_name} (CIK: {cik})...")
        
        addr_data = get_sec_data_and_geocode(cik)
        
        if addr_data:
            updates.append((
                addr_data['street1'], addr_data['street2'],
                addr_data['city'], addr_data['state'],
                addr_data['zip'], addr_data['phone'],
                addr_data['as_of'], addr_data['formatted_address'],
                addr_data['lat'], addr_data['lon'], addr_data['match_quality'],
                None, None, cik
            ))
            print(f"    ✅ Base data saved (As of: {addr_data['as_of']}) - Geolocated: {addr_data['match_quality']}")
        else:
            print("    ⚠️ Skip: No SEC data found.")

    if updates:
        print(f"\n💾 Saving {len(updates)} records to {DB_PATH}...")
        cursor.executemany("""
            UPDATE funds 
            SET address_street1 = ?, address_street2 = ?, 
                address_city = ?, address_state = ?, 
                address_zip = ?, phone = ?,
                address_as_of_date = ?, formatted_address = ?,
                lat = ?, lon = ?, match_quality = ?,
                key_employees = ?, filing_url_used = ?
            WHERE cik = ?
        """, updates)
        conn.commit()
        print("✅ Success!")
    
    conn.close()

if __name__ == "__main__":
    update_funds_table()