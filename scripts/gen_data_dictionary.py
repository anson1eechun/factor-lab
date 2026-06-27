#!/usr/bin/env python3
"""產生 data/onchain/data_dictionary.yaml — 從各 JSON 內嵌 metadata + 便宜統計自動生成，
避免人工維護漂移。純標準庫（yaml 在 base python3 即有）。

跑：python3 scripts/gen_data_dictionary.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import yaml
from core.data import data_dictionary, ONCHAIN

OUT = ONCHAIN / "data_dictionary.yaml"


def main():
    dd = data_dictionary()
    header = (
        "# 鏈上資料字典 — 由 scripts/gen_data_dictionary.py 自動生成，請勿手改。\n"
        "# 來源：data/onchain/*.json（ErcinDedeoglu, CC BY 4.0）。\n"
        f"# 序列數：{len(dd)}\n\n"
    )
    OUT.write_text(header + yaml.safe_dump(dd, allow_unicode=True, sort_keys=True), encoding="utf-8")
    print(f"寫入 {OUT}（{len(dd)} 條序列）")


if __name__ == "__main__":
    main()
