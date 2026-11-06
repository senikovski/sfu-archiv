#!/usr/bin/env python3
"""
One-time import of the original homepage cards into the Sanity "Artikel" entries.

For every article page that has a card on the homepage, the matching Artikel entry
(found by its "Bestehende Seite") gets: Darstellung (normal / hervorgehoben),
Reihenfolge (10, 20, … in the current order), card title, teaser, author and the
card image. Entries that don't exist yet are created. Other fields and entries are
left as they are.

    python3 tools/import_cards_to_sanity.py /tmp/cards.ndjson
    cd studio && npx sanity dataset import /tmp/cards.ndjson production --replace
"""
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
import build  # noqa: E402


def current_articles():
    cfg = json.loads(build.SANITY_CONFIG.read_text(encoding='utf-8'))
    url = (f"https://{cfg['projectId']}.api.sanity.io/v2024-01-01/data/query/{cfg['dataset']}?query="
           + urllib.parse.quote('*[_type == "artikel" && !(_id in path("drafts.**"))]'))
    with urllib.request.urlopen(url, timeout=60, context=build.SSL) as r:
        return json.load(r)['result']


def homepage_sequence():
    """[(slug, 'normal'|'hervorgehoben')] in the order the cards appear now, each article once."""
    T = build.TEMPLATES['home']
    normal, features = build.home_snippets()
    col_slug = {v['col']: k for k, v in normal.items()}
    titles = {p['slug']: build.plain(build.page_title(p).replace(' – ' + build.SITE['tagline'], '')).lower()
              for p in build.PAGES.values() if p['type'] == 'project'}
    seq, seen = [], set()
    keys = list(T['order'])
    for sid in keys[keys.index('section_024ab619f'):keys.index('section_38e379635')]:
        if sid == 'section_024ab619f':
            entries = [('07_artikel_rohracher', 'hervorgehoben')]
        elif sid == 'section_68e338144':
            entries = [('05_artikel_selbstvaerstaendlich_caruso', 'hervorgehoben')]
        else:
            entries = []
            section = T['order'][sid]
            for row in ({'r': section} if 'columns' in section else section).values():
                for cid, items in row['columns'].items():
                    if 'article-cards-overlay' not in (T.get(cid, {}).get('classes') or ''):
                        continue
                    if cid in col_slug:
                        entries.append((col_slug[cid], 'normal'))
                        continue
                    # duplicate card of an article: same resolution as home_snippets()
                    mods = [T[i] for i in items if i in T]
                    texts = [build.plain(m['content']['xl']) for m in mods if m['module'] == 'text']
                    title = (texts[1] if len(texts) > 1 else '').lower()
                    slug = next((s for s, t in titles.items() if title and (title in t or t in title)), None)
                    if not slug:
                        button = next((m for m in mods if m['module'] == 'button'), {})
                        slug = build.PAGES.get(str(button.get('options', {}).get('link_project')), {}).get('slug')
                    if slug:
                        entries.append((slug, 'normal'))
        for slug, kind in entries:
            if slug not in seen:
                seen.add(slug)
                seq.append((slug, kind))
    return seq, normal, features


def image(rel):
    if not rel:
        return None
    path = build.SRC / 'media' / build.nfc(rel)
    return {'_type': 'image', '_sanityAsset': f'image@{path.as_uri()}'} if path.is_file() else None


def main(out):
    build.snapshot_templates()
    seq, normal, features = homepage_sequence()
    docs = current_articles()
    by_page = {}
    for d in docs:
        if d.get('seite'):
            by_page.setdefault(d['seite'], d)
    result = []
    for i, (slug, kind) in enumerate(seq):
        pid = build.SLUGS[slug]
        page_title = build.plain(build.page_title(build.PAGES[pid]).replace(' – ' + build.SITE['tagline'], ''))
        doc = by_page.get(slug) or {'_id': f'artikel-seite-{slug.replace("_", "-")}', '_type': 'artikel',
                                    'titel': page_title, 'seite': slug}
        doc = {k: v for k, v in doc.items() if k not in ('_rev', '_createdAt', '_updatedAt')}
        card = normal.get(slug)
        feature = features.get(slug) if kind == 'hervorgehoben' else None
        src = feature or card or {}
        title = src.get('title') or doc['titel']
        doc['anzeige'] = kind
        doc['reihenfolge'] = (i + 1) * 10
        if title and title != doc.get('titel'):
            doc['kachelTitel'] = title
        doc['teaser'] = (card or {}).get('teaser') or src.get('teaser') or doc.get('teaser') or ''
        doc['autor'] = doc.get('autor') or src.get('author') or ''
        img = image(src.get('image'))
        if img:
            doc['kachelbild'] = img
        result.append(doc)
        print(f"  {doc['reihenfolge']:4} {kind:13} {slug:52} {title}")
    with open(out, 'w', encoding='utf-8') as f:
        for d in result:
            f.write(json.dumps(d, ensure_ascii=False) + '\n')
    print(f'wrote {out}: {len(result)} Artikel')


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else 'cards.ndjson')
