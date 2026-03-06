import re

with open('tabs/tab1_universe_overview.py', 'r') as f:
    content = f.read()

new_text = """    selected_backtest_funds = st.multiselect(
        "Select up to 10 funds for the crowded index backtest:",
        options=all_funds,
        default=default_funds,
        max_selections=10,
        key="crowded_backtest_funds"
    )

    st.markdown('''
    **How the Crowded Index Works:**
    * **Universe:** We look at regular stock shares (not options) held by the funds you selected above.
    * **Ranking:** Stocks are scored based on two main factors:
        1. **Popularity:** How many of the selected funds own the stock.
        2. **Conviction:** The average size of the position relative to the funds' total assets.
    * **Selection:** We combine these two scores. The 5 stocks with the best overall score (highest popularity and conviction combined) are chosen as the "Crowded Index" for that quarter.
    * **Performance:** We then calculate the returns as if we invested an equal amount of money into each of these 5 stocks. The **Shadow Index** shows what happens if you bought those same 5 stocks, but waited 60 days after the quarter ended to buy them.
    ''')

    if not selected_backtest_funds:"""

old_text = """    selected_backtest_funds = st.multiselect(
        "Select up to 10 funds for the crowded index backtest:",
        options=all_funds,
        default=default_funds,
        max_selections=10,
        key="crowded_backtest_funds"
    )

    if not selected_backtest_funds:"""

if old_text in content:
    content = content.replace(old_text, new_text)
    with open('tabs/tab1_universe_overview.py', 'w') as f:
        f.write(content)
    print("Added the Crowded Index explanation text successfully.")
else:
    print("Could not find the target location to add explanation text.")
