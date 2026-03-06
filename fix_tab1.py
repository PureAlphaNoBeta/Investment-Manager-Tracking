import re

with open('tabs/tab1_universe_overview.py', 'r') as f:
    content = f.read()

# 1. Remove Crowded Index Backtest section from its current location
pattern_remove = r"    st\.subheader\(\"Crowded Index Backtest\"\).*?(?=    st\.subheader\(\"Universe Snapshot\"\))"
match = re.search(pattern_remove, content, re.DOTALL)

if match:
    crowded_section = match.group(0)
    content = content.replace(crowded_section, "")

    # 2. Append it to the end of the file
    content += "\n" + crowded_section

    with open('tabs/tab1_universe_overview.py', 'w') as f:
        f.write(content)
    print("Successfully moved Crowded Index Backtest to the bottom.")
else:
    print("Could not find the Crowded Index Backtest section.")
