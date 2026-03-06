import os

with open("tabs/tab1_universe_overview.py", "r") as f:
    lines = f.readlines()

# find index of st.subheader("Crowded Index Backtest")
start_idx = -1
for i, line in enumerate(lines):
    if 'st.subheader("Crowded Index Backtest")' in line:
        start_idx = i
        break

# find index of st.subheader("Universe Snapshot")
end_idx = -1
for i, line in enumerate(lines):
    if 'st.subheader("Universe Snapshot")' in line:
        end_idx = i
        break

if start_idx != -1 and end_idx != -1:
    section_to_move = lines[start_idx:end_idx]
    before_section = lines[:start_idx]
    after_section = lines[end_idx:]

    new_lines = before_section + after_section + ["\n", "    st.markdown(\"---\")\n"] + section_to_move

    with open("tabs/tab1_universe_overview.py", "w") as f:
        f.writelines(new_lines)
    print("Successfully moved.")
else:
    print(f"Could not find indices. start: {start_idx}, end: {end_idx}")
