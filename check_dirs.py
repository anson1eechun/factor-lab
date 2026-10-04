import os, glob

vault = "/home/anson/Documents/Obsidian Vault/量化交易"
fl = "/home/anson/factor-lab"

for d in [vault, fl]:
    print(f"--- {d} ---")
    print("exists:", os.path.exists(d))
    if os.path.exists(d):
        print("entries:", os.listdir(d)[:30])
