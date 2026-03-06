import os

with open("tabs/tab1_universe_overview.py", "r") as f:
    content = f.read()

content = content.replace("\\`owner_rank\\`", "`owner_rank`")
content = content.replace("\\`weight_rank\\`", "`weight_rank`")
content = content.replace("\\`total_rank\\`", "`total_rank`")

with open("tabs/tab1_universe_overview.py", "w") as f:
    f.write(content)
print("Successfully fixed.")
