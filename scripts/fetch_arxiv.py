#!/usr/bin/env python3
"""Quick helper: fetch arXiv abstract + extra metadata for a given arXiv ID."""
import sys, urllib.request, xml.etree.ElementTree as ET
from html import unescape

def fetch_arxiv_abstract(arxiv_id: str):
    # Normalize: "2501.06758v2" or "arXiv:2501.06758v2"
    aid = arxiv_id.replace("arXiv:", "").strip()
    url = f"http://export.arxiv.org/api/query?id_list={aid}"
    req = urllib.request.Request(url, headers={"User-Agent": "FactorLab-Extractor/1.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = resp.read()
    root = ET.fromstring(data.decode("utf-8"))
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    entry = root.find("atom:entry", namespaces=ns)
    if entry is None:
        print("No entry found")
        return
    title = unescape((entry.find("atom:title", namespaces=ns).text or "").strip())
    summary = unescape((entry.find("atom:summary", namespaces=ns).text or "").strip())
    authors = [
        unescape(a.find("atom:name", namespaces=ns).text.strip())
        for a in entry.findall("atom:author", namespaces=ns)
    ]
    updated = (entry.find("atom:updated", namespaces=ns).text or "").strip()
    print("TITLE:", title)
    print("AUTHORS:", "; ".join(authors))
    print("UPDATED:", updated)
    print("SUMMARY:", summary)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python fetch_arxiv.py <arxiv_id>")
        sys.exit(1)
    fetch_arxiv_abstract(sys.argv[1])
