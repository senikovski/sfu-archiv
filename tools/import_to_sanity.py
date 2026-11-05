#!/usr/bin/env python3
"""
One-time import of the Personen/Orte databases (source/data/*.csv) into Sanity.

Writes an NDJSON file that the Sanity CLI imports, including the portrait and
place images:

    python3 tools/import_to_sanity.py /tmp/archiv.ndjson
    cd studio && npx sanity dataset import /tmp/archiv.ndjson production --replace

Document ids are derived from the names, so running it again with --replace
updates the same entries instead of creating duplicates.
"""
import csv
import difflib
import json
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / 'source'
sys.path.insert(0, str(ROOT / 'tools'))
import build  # noqa: E402  (reuses the article-link resolution and file-name rules)


def slug(text):
    text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode().lower()
    return re.sub(r'[^a-z0-9]+', '-', text).strip('-')


def split_list(s):
    return [x.strip() for x in (s or '').split('.') if x.strip()]


def image(rel):
    path = SRC / 'media' / build.nfc(rel)
    return {'_type': 'image', '_sanityAsset': f'image@{path.as_uri()}'} if path.is_file() else None


def ref(doc_id, key):
    return {'_type': 'reference', '_ref': doc_id, '_key': key}


def main(out):
    personen = build.read_csv('personen.csv')
    orte = build.read_csv('orte.csv')
    docs = []
    report = []

    # ---- Artikel: every title referenced from the CSVs, linked to its page if it exists
    artikel_ids = {}

    def artikel_ref(row, i, key):
        title = (row.get(f'Artikel{i}') or '').strip()
        if len(title) <= 3:
            return None
        doc_id = f'artikel-{slug(title)}'
        if doc_id not in artikel_ids:
            pid = build.article_link(row.get(f'artikel{i}Href'), title)
            doc = {'_id': doc_id, '_type': 'artikel', 'titel': title, 'autor': (row.get(f'Autor{i}') or '').strip()}
            if pid:
                doc['seite'] = build.PAGES[pid]['slug']
            artikel_ids[doc_id] = doc
        return ref(doc_id, key)

    # ---- name lookup with typo / variant tolerance
    person_ids = {r['Name'].strip(): f"person-{slug(r['Name'].strip())}" for r in personen}
    ort_ids = {r['Ort'].strip(): f"ort-{slug(r['Ort'].strip())}" for r in orte}

    def match_person(name):
        if name in person_ids:
            return person_ids[name]
        close = difflib.get_close_matches(name, person_ids, n=1, cutoff=0.85)
        if close:
            report.append(f'Person "{name}" → "{close[0]}"')
            return person_ids[close[0]]
        report.append(f'Person "{name}": kein Eintrag, weggelassen')
        return None

    def match_ort(name):
        if name in ort_ids:
            return ort_ids[name]
        for known in ort_ids:
            if known in name or name in known:
                report.append(f'Ort "{name}" → "{known}"')
                return ort_ids[known]
        return None

    for i, row in enumerate(personen):
        name = row['Name'].strip()
        file_name = f"{i:02d}_{build.replace_umlaute(name.replace(' ', '_'))}.png"
        doc = {
            '_id': person_ids[name], '_type': 'person', 'name': name,
            'jahre': row['Jahr'].strip(), 'text': row['Text'].strip(), 'reihenfolge': i + 1,
        }
        portrait, thumb = image(f'2021/11/{file_name}'), image(f'2021/11/Thumbnail_{file_name}')
        if portrait:
            doc['portrait'] = portrait
        if thumb:
            doc['thumbnail'] = thumb
        doc['artikel'] = [r for k in range(1, 5) if (r := artikel_ref(row, k, f'a{k}'))]
        doc['personen'] = [ref(pid, f'p{k}') for k, n in enumerate(split_list(row['Personen'])) if (pid := match_person(n)) and pid != doc['_id']]
        orte_refs, weitere = [], []
        for k, n in enumerate(split_list(row['Orte'])):
            oid = match_ort(n)
            if oid:
                if all(r['_ref'] != oid for r in orte_refs):
                    orte_refs.append(ref(oid, f'o{k}'))
            else:
                weitere.append(n)
                report.append(f'Ort "{n}" (bei {name}): kein Karteneintrag → "Weitere Orte"')
        doc['orte'] = orte_refs
        if weitere:
            doc['weitereOrte'] = weitere
        docs.append(doc)

    for i, row in enumerate(orte):
        name = row['Ort'].strip()
        doc = {
            '_id': ort_ids[name], '_type': 'ort', 'name': name, 'text': row['Text'].strip(),
            # the CSV columns are swapped: "Long" holds the latitude
            'lage': {'lat': float(row['Long']), 'lng': float(row['Lat'])},
            'adresse': ', '.join(x.strip() for x in (row.get('Adresse') or '', row.get('') or '') if x and x.strip()),
            'reihenfolge': i + 1,
        }
        bild = image('2021/11/' + row['imgSrc'])
        if bild:
            doc['bild'] = bild
        doc['artikel'] = [r for k in range(1, 16) if (r := artikel_ref(row, k, f'a{k}'))]
        doc['personen'] = [ref(pid, f'p{k}') for k, n in enumerate(split_list(row['Personen'])) if (pid := match_person(n))]
        docs.append(doc)

    docs = list(artikel_ids.values()) + docs
    with open(out, 'w', encoding='utf-8') as f:
        for d in docs:
            f.write(json.dumps(d, ensure_ascii=False) + '\n')
    counts = {t: sum(d['_type'] == t for d in docs) for t in ('person', 'ort', 'artikel')}
    print(f'wrote {out}: {counts}')
    for line in sorted(set(report)):
        print('  ' + line)


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else 'archiv.ndjson')
