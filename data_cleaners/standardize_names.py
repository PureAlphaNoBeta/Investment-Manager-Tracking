import sqlite3
import pandas as pd
import os

def standardize_issuer_names():
    db_path = os.path.join("data", "hedge_funds.db")
    if not os.path.exists(db_path):
        print("❌ Database not found.")
        return

    conn = sqlite3.connect(db_path)
    print("🔍 Scanning database for the most recent company names by CUSIP...")

    # 1. Pull all CUSIPs and Names, ordered by the newest report_date first
    query = """
        SELECT cusip, name_of_issuer
        FROM holdings
        WHERE name_of_issuer IS NOT NULL
        ORDER BY report_date DESC
    """
    df_all_names = pd.read_sql(query, conn)

    # 2. Keep only the first occurrence of each CUSIP (which is the most recent name)
    df_latest_names = df_all_names.drop_duplicates(subset=['cusip'], keep='first').copy()
    
    # Optional: You can still apply a light uppercase/strip here just to ensure the 
    # absolute latest name doesn't have weird trailing spaces from the SEC XML
    df_latest_names['name_of_issuer'] = df_latest_names['name_of_issuer'].str.upper().str.strip()

    print(f"✅ Found {len(df_latest_names)} unique CUSIPs. Synchronizing historical records...")

    # 3. Update the database efficiently using executemany
    cursor = conn.cursor()
    
    # We turn the dataframe into a list of tuples: (new_name, cusip)
    update_data = list(zip(df_latest_names['name_of_issuer'], df_latest_names['cusip']))
    
    cursor.executemany("""
        UPDATE holdings
        SET name_of_issuer = ?
        WHERE cusip = ?
    """, update_data)

    conn.commit()
    conn.close()
    
    print("🎉 Success! All historical company names have been perfectly aligned to their most recent filings.")

if __name__ == "__main__":
    standardize_issuer_names()