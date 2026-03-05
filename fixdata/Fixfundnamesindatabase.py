import sqlite3
import os

# Path to the database
DB_PATH = os.path.join("data", "hedge_funds.db")

# --- CONFIGURATION ---
OLD_NAME = "Gate Foundation"
NEW_NAME = "Gates Foundation"

def fix_fund_name():
    """
    Updates the fund name from OLD_NAME to NEW_NAME 
    in both the 'holdings' and 'funds' tables.
    """
    if not os.path.exists(DB_PATH):
        print(f"❌ Database not found at: {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    print(f"🔍 Scanning database for '{OLD_NAME}'...")
    
    # 1. Update 'holdings' table
    cursor.execute("SELECT COUNT(*) FROM holdings WHERE fund_name = ?", (OLD_NAME,))
    holdings_count = cursor.fetchone()[0]
    
    if holdings_count > 0:
        print(f"  -> Found {holdings_count} records in 'holdings'. Updating...")
        cursor.execute("UPDATE holdings SET fund_name = ? WHERE fund_name = ?", (NEW_NAME, OLD_NAME))
    else:
        print("  -> No records found in 'holdings'.")

    # 2. Update 'funds' table (Metadata table)
    cursor.execute("SELECT COUNT(*) FROM funds WHERE fund_name = ?", (OLD_NAME,))
    funds_count = cursor.fetchone()[0]
    
    if funds_count > 0:
        print(f"  -> Found {funds_count} records in 'funds'. Updating...")
        cursor.execute("UPDATE funds SET fund_name = ? WHERE fund_name = ?", (NEW_NAME, OLD_NAME))
    else:
        print("  -> No records found in 'funds'.")
    
    conn.commit()
    conn.close()
    print("✅ Database correction complete.")

if __name__ == "__main__":
    fix_fund_name()