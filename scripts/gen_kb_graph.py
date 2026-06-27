#!/usr/bin/env python3
"""產生 reports/kb_graph.html — factor-lab 知識圖譜（純標準庫，真實 index.db + graveyard）。

跑：python3 scripts/gen_kb_graph.py
也由 Balaena :8900 控制台的 /graph 路由即時呼叫 core.kb_graph。
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pathlib import Path
from core.kb_graph import build_graph, render_html


def main():
    g = build_graph()
    out = Path(__file__).resolve().parent.parent / "reports" / "kb_graph.html"
    out.parent.mkdir(exist_ok=True)
    out.write_text(render_html(g), encoding="utf-8")
    print(f"寫入 {out}｜{g['stats']}")


if __name__ == "__main__":
    main()
