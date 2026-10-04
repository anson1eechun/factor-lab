#!/usr/bin/env python3
import json
from pathlib import Path

vault = Path("/home/anson/Documents/Obsidian Vault/量化交易")
paper_dir = vault / "06-书籍论文"
factor_dir = vault / "10-因子库"

result = {
    "vault_exists": vault.exists(),
    "paper_dir_exists": paper_dir.exists(),
    "factor_dir_exists": factor_dir.exists(),
    "papers": [],
    "factors": [],
}

if paper_dir.exists():
    result["papers"] = [
        str(p.relative_to(vault))
        for p in sorted(paper_dir.glob("*.md"))
    ]

if factor_dir.exists():
    result["factors"] = [
        str(p.relative_to(vault))
        for p in sorted(factor_dir.glob("*.md"))
    ]

with open("/home/anson/factor-lab/vault_scan_out.txt", "w", encoding="utf-8") as f:
    f.write(json.dumps(result, ensure_ascii=False, indent=2))
