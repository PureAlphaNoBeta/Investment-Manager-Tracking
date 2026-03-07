import sqlite3
import pandas as pd

def main():
    db_path = './data/hedge_funds.db'
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    print("Connecting to database and identifying missing sectors...")

    # We will fetch a unique mapping of ticker to name_of_issuer from the holdings table.
    query = """
    SELECT DISTINCT c.ticker, h.name_of_issuer, c.sector
    FROM company_info c
    LEFT JOIN holdings h ON c.ticker = h.ticker
    WHERE c.sector IS NULL OR c.sector = ''
    """
    df_missing = pd.read_sql(query, conn)

    print(f"Found {len(df_missing['ticker'].unique())} unique tickers with missing or empty sectors.")

    # Identify the ACQ companies
    is_acq = df_missing['name_of_issuer'].str.contains('ACQUISITION|ACQUISTN|SPAC|ACQ', case=False, na=False)

    # The same ticker could have multiple names in holdings over time, so we take the max of the boolean mask per ticker
    df_missing['is_acq'] = is_acq
    acq_tickers_df = df_missing.groupby('ticker')['is_acq'].max().reset_index()

    acq_tickers = acq_tickers_df[acq_tickers_df['is_acq'] == True]['ticker'].tolist()
    unknown_tickers = acq_tickers_df[acq_tickers_df['is_acq'] == False]['ticker'].tolist()

    print(f"Identified {len(acq_tickers)} ACQ Corps / SPACs.")
    print(f"Identified {len(unknown_tickers)} other companies defaulting to 'Unknown'.")

    # Update the database
    print("\nUpdating database...")

    if acq_tickers:
        # SQLite IN clause has a limit (usually 999), so we do it in batches
        batch_size = 500
        for i in range(0, len(acq_tickers), batch_size):
            batch = acq_tickers[i:i+batch_size]
            placeholders = ','.join(['?'] * len(batch))
            cursor.execute(f"UPDATE company_info SET sector = 'ACQ Corps / SPACs' WHERE ticker IN ({placeholders})", batch)

    if unknown_tickers:
        batch_size = 500
        for i in range(0, len(unknown_tickers), batch_size):
            batch = unknown_tickers[i:i+batch_size]
            placeholders = ','.join(['?'] * len(batch))
            cursor.execute(f"UPDATE company_info SET sector = 'Unknown' WHERE ticker IN ({placeholders})", batch)

    # Finally, to catch any tickers in company_info that aren't in holdings at all (just in case)
    cursor.execute("UPDATE company_info SET sector = 'Unknown' WHERE sector IS NULL OR sector = ''")

    conn.commit()
    conn.close()

    print("Database update complete! You should now run the dashboard without any on-the-fly imputation in app.py.")

if __name__ == "__main__":
    main()
