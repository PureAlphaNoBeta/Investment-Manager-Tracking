import os

with open("tabs/tab1_universe_overview.py", "r") as f:
    lines = f.readlines()

insert_idx = -1
for i, line in enumerate(lines):
    if 'key="crowded_backtest_funds"' in line:
        insert_idx = i + 2
        break

if insert_idx != -1:
    markdown_text = """    st.markdown('''
    **Index Definition & Calculation Logic:**
    * **Universe:** SHARE positions of the selected funds that have available price data.
    * **Weighting:** The position size is adjusted by dividing its standardized market value by the fund's total valid AUM.
    * **Ranking:** Stocks are ranked by two metrics:
        1. Number of unique funds owning the stock (\`owner_rank\`).
        2. Average adjusted weight across the owning funds (\`weight_rank\`).
    * **Selection:** The two ranks are summed to yield a \`total_rank\`. The top 5 stocks with the lowest total rank are selected as index constituents for the quarter.
    * **Performance:** Returns are calculated on an equal-weighted basis. The **Shadow Index** reflects entering the same positions but with a 60-day lag.
    ''')
"""
    new_lines = lines[:insert_idx] + [markdown_text] + lines[insert_idx:]
    with open("tabs/tab1_universe_overview.py", "w") as f:
        f.writelines(new_lines)
    print("Successfully inserted.")
else:
    print("Could not find insertion point.")
