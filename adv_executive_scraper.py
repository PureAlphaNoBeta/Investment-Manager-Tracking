import sqlite3
import pandas as pd
import zipfile
import gzip
import shutil
import os
import re
import xml.etree.ElementTree as ET

# Configuration
DB_PATH = os.path.join("data", "hedge_funds.db")

def clean_name(name):
    if not isinstance(name, str): 
        return ""
    name = re.sub(r'[^\w\s]', '', name)
    return ' '.join(name.upper().split())

def super_clean_name(name):
    if not isinstance(name, str): 
        return ""
    return re.sub(r'\W+', '', name).upper()

def normalize_cik(cik):
    """
    Strips leading zeros so CIKs match perfectly.
    """
    if not cik:
        return ""
    return str(cik).strip().lstrip('0')

def extract_xml_from_archive():
    zip_path = os.path.join("data", "SEC_Investment_Adviser_Report.zip")
    gz_path = os.path.join("data", "SEC_Investment_Adviser_Report.gz")
    raw_xml_path = os.path.join("data", "SEC_Investment_Adviser_Report.xml")
    
    extract_path = os.path.join("data", "iapd_data.xml")

    if os.path.exists(raw_xml_path):
        print("📦 Found raw XML file! No extraction needed.")
        return raw_xml_path

    if os.path.exists(gz_path):
        print("📦 Found .gz archive! Extracting XML (please wait)...")
        try:
            with gzip.open(gz_path, 'rb') as f_in:
                with open(extract_path, 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out)
            return extract_path
        except Exception as e:
            print(f"❌ Error extracting the .gz file: {e}")
            return None

    if os.path.exists(zip_path):
        print("📦 Found .zip archive! Extracting XML (please wait)...")
        try:
            with zipfile.ZipFile(zip_path, 'r') as z:
                xml_filename = z.namelist()[0]
                with open(extract_path, "wb") as f:
                    f.write(z.read(xml_filename))
            return extract_path
        except Exception as e:
            print(f"❌ Error extracting the .zip file: {e}")
            return None

    print(f"❌ Could not find the SEC report in your 'data' folder.")
    return None

def build_executive_maps(xml_path):
    """
    Builds TWO maps: One strictly by CIK, and one by fuzzy name.
    Uses ultra-forgiving attribute and tag matching to defeat SEC abbreviations.
    """
    print("  -> Parsing SEC Form ADV XML (this takes about 15-30 seconds)...")
    
    cik_map = {}
    name_map = {}
    
    context = ET.iterparse(xml_path, events=('end',))
    
    for event, elem in context:
        # Strip the invisible XML namespace
        tag = elem.tag.split('}')[-1] 
        
        if tag == 'Firm':
            info_elem = None
            owners = []
            private_funds = []
            
            # Ultra-forgiving scan of all children
            for desc in elem.iter():
                desc_tag = desc.tag.split('}')[-1].lower()
                
                if desc_tag == 'info':
                    info_elem = desc
                # Catch "Owner", "DirectOwner", "DrctOwnr", "Executive", etc.
                elif 'own' in desc_tag or 'exec' in desc_tag or 'officer' in desc_tag:
                    owners.append(desc)
                elif 'fund' in desc_tag:
                    private_funds.append(desc)
            
            if info_elem is None:
                elem.clear()
                continue
                
            # Grab Name and CIK regardless of how they abbreviated the attribute
            raw_adviser_name = info_elem.get('BusNm') or info_elem.get('LegalNm') or info_elem.get('BusName') or ''
            adviser_name = clean_name(raw_adviser_name)
            
            raw_cik = info_elem.get('CIK') or info_elem.get('Cik') or info_elem.get('cik') or ''
            adviser_cik = normalize_cik(raw_cik)
            
            executives = []
            for owner in owners:
                # Catch Name and Title abbreviations
                name = owner.get('DeNm') or owner.get('Nm') or owner.get('Name') or ''
                title = owner.get('Title') or owner.get('Dtll') or owner.get('Ttl') or ''
                
                if name:
                    # Fix reversed names like "DRUCKENMILLER, STANLEY"
                    name_parts = name.split(',')
                    if len(name_parts) >= 2:
                        clean_exec_name = f"{name_parts[1].strip()} {name_parts[0].strip()}".title()
                    else:
                        clean_exec_name = name.title()
                        
                    # Only append title if they have one
                    if title:
                        executives.append(f"{clean_exec_name} ({title.title()})")
                    else:
                        executives.append(clean_exec_name)
            
            # Remove exact duplicates (sometimes SEC lists the same person twice)
            executives = list(dict.fromkeys(executives))
            exec_str = "; ".join(executives) if executives else None
            
            if exec_str:
                # 1. Map by exact CIK (The Gold Standard)
                if adviser_cik:
                    cik_map[adviser_cik] = exec_str
                
                # 2. Map by Name (The Fallback)
                if adviser_name:
                    name_map[adviser_name] = exec_str
                
                # Map the underlying private funds to the fallback engine
                for pf in private_funds:
                    raw_pf_name = pf.get('Nm') or pf.get('Name') or ''
                    pf_name = clean_name(raw_pf_name)
                    if pf_name:
                        name_map[pf_name] = exec_str
                        
            # Free memory immediately so the script doesn't crash
            elem.clear()
            
    return cik_map, name_map

def update_executives():
    if not os.path.exists(DB_PATH):
        print(f"❌ Database not found at: {DB_PATH}")
        return

    xml_path = extract_xml_from_archive()
    if not xml_path:
        return

    cik_map, name_map = build_executive_maps(xml_path)
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        df_funds = pd.read_sql("SELECT fund_name, cik FROM funds", conn)
    except Exception as e:
        print(f"❌ Error reading table: {e}")
        conn.close()
        return
    
    print(f"\n🔍 Matching {len(df_funds)} funds using CIK and Form ADV data...")
    updates = []
    
    for index, row in df_funds.iterrows():
        original_name = row['fund_name']
        raw_cik = row['cik']
        
        normalized_cik = normalize_cik(raw_cik)
        search_target = super_clean_name(original_name)
        
        match_found = False
        
        # ENGINE 1: Check by exact CIK first!
        if normalized_cik and normalized_cik in cik_map:
            execs = cik_map[normalized_cik]
            print(f"  ✅ CIK Match found for: {original_name}")
            print(f"     👔 {execs[:80]}...")
            updates.append((execs, "https://adviserinfo.sec.gov/", raw_cik))
            match_found = True
            
        # ENGINE 2: Fallback to Name Matching if CIK fails
        elif not match_found:
            # Check exact name match
            exact_name = clean_name(original_name)
            if exact_name in name_map:
                execs = name_map[exact_name]
                print(f"  ✅ Exact Name Match for: {original_name}")
                print(f"     👔 {execs[:80]}...")
                updates.append((execs, "https://adviserinfo.sec.gov/", raw_cik))
                match_found = True
            elif len(search_target) >= 4:
                # Check fuzzy substring match
                for sec_name, executives in name_map.items():
                    sec_target = super_clean_name(sec_name)
                    if search_target in sec_target or sec_target in search_target:
                        print(f"  ✅ Fuzzy Match: {original_name} -> {sec_name}")
                        print(f"     👔 {executives[:80]}...")
                        updates.append((executives, "https://adviserinfo.sec.gov/", raw_cik))
                        match_found = True
                        break
                        
        if not match_found:
            print(f"  ⚠️ No ADV match found for: {original_name} (CIK: {raw_cik})")

    if updates:
        print(f"\n💾 Updating {len(updates)} records in database...")
        cursor.executemany("""
            UPDATE funds 
            SET key_employees = ?,
                filing_url_used = ?
            WHERE cik = ?
        """, updates)
        conn.commit()
        print("✅ Success!")
    else:
        print("\nℹ️ No updates were made to the database.")
        
    conn.close()
    
    try:
        if xml_path == os.path.join("data", "iapd_data.xml") and os.path.exists(xml_path):
            os.remove(xml_path)
            print("🗑️ Cleaned up temporary extracted XML file.")
    except Exception as e:
        pass

if __name__ == "__main__":
    update_executives()