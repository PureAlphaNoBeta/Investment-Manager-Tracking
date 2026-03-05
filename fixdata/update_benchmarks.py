import pandas as pd
import sqlite3
import os

def update_benchmarks_from_excel(excel_path, db_path, table_name='benchmarks'):
    """
    Reads benchmark data from an Excel file and replaces the data in a SQLite table.
    It assumes the data is in the first sheet and the columns are in the order:
    Date, SPY, URTH, ^IRX.

    Args:
        excel_path (str): The full path to the Excel file.
        db_path (str): The path to the SQLite database file.
        table_name (str): The name of the table to update. Defaults to 'benchmarks'.
    """
    try:
        # 1. Read the data from the first sheet of the Excel file
        print(f"Reading data from '{excel_path}' (first sheet)...")
        # Use header=None because the user didn't specify if there are headers
        df = pd.read_excel(excel_path, sheet_name=0, header=0)
        
        # 2. Select the first four columns and assign names
        # The user said: "The first column are the dates followed by SPY, URTH and ^IRX"
        if df.shape[1] < 4:
            print("Error: The Excel file needs to have at least 4 columns for Date, SPY, URTH, and ^IRX.")
            return

        # Take the first 4 columns
        benchmark_df = df.iloc[:, :4]
        
        # Rename columns for clarity and consistency
        column_names = ['Date', 'SPY', 'URTH', '^IRX']
        benchmark_df.columns = column_names
        
        # 3. Ensure 'Date' column is in datetime format
        benchmark_df['Date'] = pd.to_datetime(benchmark_df['Date'])
        
        # 4. Connect to the SQLite database
        print(f"Connecting to database at '{db_path}'...")
        conn = sqlite3.connect(db_path)
        
        # 5. Write the data to the 'benchmarks' table, replacing existing data
        print(f"Writing data to the '{table_name}' table. This will replace all existing data in the table.")
        benchmark_df.to_sql(table_name, conn, if_exists='replace', index=False)
        
        conn.close()
        
        print(f"Successfully updated the '{table_name}' table in '{db_path}'.")

    except FileNotFoundError:
        print(f"Error: The file was not found at '{excel_path}'")
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == '__main__':
    # --- Configuration ---
    # The user specified the file is named 'funds_benchmarks' and is in the 'data' folder
    EXCEL_FILE_PATH = os.path.join("data", "funds_benchmarks.xlsx")
    DATABASE_PATH = os.path.join("data", "hedge_funds.db")
    
    # --- Run the update ---
    update_benchmarks_from_excel(EXCEL_FILE_PATH, DATABASE_PATH)
