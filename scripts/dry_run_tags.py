#!/usr/bin/env python3
"""Dry run: show what tag changes would be made."""
import yaml, re
from pathlib import Path

BASE = Path('/home/anson/Documents/Obsidian Vault/量化交易/06-书籍论文')
SYS_PATH = '/home/anson/factor-lab/scripts/standardize_tags.py'

# Import the CN_TO_EN mapping from the main script
import importlib.util, sys
spec = importlib.util.spec_from_file_location("std_tags", SYS_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
CN_TO_EN = mod.CN_TO_EN

changes = []
auto_tag_changes = []

for md_file in sorted(BASE.rglob('*.md')):
    if md_file.name in ('paper_insights.md', 'gap_analysis.md'):
        continue
    text = md_file.read_text(encoding='utf-8')
    fm_match = re.search(r'^---\s*\n(.*?)\n---', text, re.DOTALL)
    if not fm_match:
        continue
    try:
        fm = yaml.safe_load(fm_match.group(1))
    except:
        continue
    if not fm or 'tags' not in fm:
        continue
    tags = fm['tags']
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(',') if t.strip()]
    if not isinstance(tags, list):
        tags = [str(tags)]
    
    old_set = set(str(t).strip() for t in tags)
    new_set = set()
    for t in old_set:
        if t in CN_TO_EN:
            new_set.add(CN_TO_EN[t])
        else:
            new_set.add(t)
    
    if old_set != new_set:
        rel = md_file.relative_to(BASE)
        removed = old_set - new_set
        added = new_set - old_set
        changes.append(f'{rel}: {removed} → {added}')
    
    # Check auto-tag
    title = fm.get('title', '')
    existing_topics = new_set - {'arxiv', '待精讀', 'ICML2026'}
    if not existing_topics and title:
        # Simulate auto-tag
        title_lower = title.lower()
        auto = set()
        for keywords, tag in mod.TITLE_KEYWORD_TAGS:
            for kw in keywords:
                if kw.lower() in title_lower:
                    auto.add(tag)
                    break
        if auto:
            auto_tag_changes.append(f'{md_file.relative_to(BASE)}: +{auto}')

print(f'=== TAG TRANSLATION CHANGES ({len(changes)} files) ===')
for c in changes:
    print(f'  {c}')

print(f'\n=== AUTO-TAG ({len(auto_tag_changes)} files) ===')
for c in auto_tag_changes:
    print(f'  {c}')
