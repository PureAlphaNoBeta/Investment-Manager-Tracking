import re

file_path = "tabs/tab1_universe_overview.py"

with open(file_path, "r") as f:
    content = f.read()

old_text = """    **Index Definition & Calculation Logic:**
    * **Universe:** SHARE positions of the selected funds that have available price data.
    * **Weighting:** The position size is adjusted by dividing its standardized market value by the fund's total valid AUM.
    * **Ranking:** Stocks are ranked by two metrics:
        1. Number of unique funds owning the stock (`owner_rank`).
        2. Average adjusted weight across the owning funds (`weight_rank`).
    * **Selection:** The two ranks are summed to yield a `total_rank`. The top 5 stocks with the lowest total rank are selected as index constituents for the quarter.
    * **Performance:** Returns are calculated on an equal-weighted basis. The **Shadow Index** reflects entering the same positions but with a 60-day lag."""

new_text = """    **How the Crowded Index Works:**
    * **Universe:** We look at regular stock shares (not options) held by the funds you selected above.
    * **Ranking:** Stocks are scored based on two main factors:
        1. **Popularity:** How many of the selected funds own the stock.
        2. **Conviction:** The average size of the position relative to the funds' total assets.
    * **Selection:** We combine these two scores. The 5 stocks with the best overall score (highest popularity and conviction combined) are chosen as the "Crowded Index" for that quarter.
    * **Performance:** We then calculate the returns as if we invested an equal amount of money into each of these 5 stocks. The **Shadow Index** shows what happens if you bought those same 5 stocks, but waited 60 days after the quarter ended to buy them."""

content = content.replace(old_text, new_text)

with open(file_path, "w") as f:
    f.write(content)
