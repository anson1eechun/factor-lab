#!/usr/bin/env python3
"""Analyze tags across all papers in the quantitative trading vault."""
import yaml
import re
from pathlib import Path
from collections import Counter

base = Path('/home/anson/Documents/Obsidian Vault/量化交易/06-书籍论文')
workflow_tags = {'arxiv', '待精讀', '論文', 'paper', 'reading-list', 'todo', 'done', '精读', '已读', '未读'}
all_tags = Counter()
papers_need_topic = []
papers_chinese = []
paper_data = {}  # relpath -> {tags, has_topic}

for md_file in sorted(base.rglob('*.md')):
    name = md_file.name
    if name in ('paper_insights.md', 'gap_analysis.md'):
        continue
    
    text = md_file.read_text(encoding='utf-8')
    
    fm_match = re.search(r'^---\s*\n(.*?)\n---', text, re.DOTALL)
    if not fm_match:
        papers_need_topic.append(f'NO_FM: {md_file.relative_to(base)}')
        continue
    
    try:
        fm = yaml.safe_load(fm_match.group(1))
    except Exception:
        papers_need_topic.append(f'YAML_ERR: {md_file.relative_to(base)}')
        continue
    
    if not fm or 'tags' not in fm:
        papers_need_topic.append(f'NO_TAGS: {md_file.relative_to(base)}')
        continue
    
    tags = fm['tags']
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(',') if t.strip()]
    if not isinstance(tags, list):
        tags = [str(tags)]
    
    has_chinese = False
    clean_tags = []
    for tag in tags:
        tag_s = str(tag).strip()
        if tag_s:
            clean_tags.append(tag_s)
            all_tags[tag_s] += 1
            if any('\u4e00' <= c <= '\u9fff' for c in tag_s):
                has_chinese = True
    
    if has_chinese:
        papers_chinese.append(str(md_file.relative_to(base)))
    
    topic_tags = [t for t in clean_tags if t.lower() not in workflow_tags]
    paper_data[str(md_file.relative_to(base))] = {
        'tags': clean_tags,
        'has_topic': bool(topic_tags),
        'title': fm.get('title', ''),
    }
    
    if not topic_tags:
        papers_need_topic.append(str(md_file.relative_to(base)))

print(f'TOTAL_PAPERS: {sum(1 for _ in base.rglob("*.md")) - 2}')
print(f'TOTAL_UNIQUE_TAGS: {len(all_tags)}')
print(f'TOTAL_OCCURRENCES: {sum(all_tags.values())}')
print(f'NEED_TOPIC: {len(papers_need_topic)}')
print(f'CHINESE_TAG_PAPERS: {len(papers_chinese)}')

print('\n=== TOP 30 TAGS ===')
for tag, count in all_tags.most_common(30):
    print(f'  {count:4d}  {tag}')

print('\n=== CHINESE TAGS ===')
for tag, count in sorted(all_tags.items(), key=lambda x: -x[1]):
    if any('\u4e00' <= ch <= '\u9fff' for ch in str(tag)):
        print(f'  {count:4d}  {tag}')

print('\n=== PAPERS NEEDING TOPIC TAGS ===')
for p in papers_need_topic:
    print(f'  {p}')
