#!/usr/bin/env python3
"""
One-time migration: export the old Semplice/WordPress site into ./source

Reads the newest All-in-One-WP-Migration backup (.wpress) of the old local
Laragon install, pulls the database out of it and writes:

  source/content.json      pages, articles, footer, media index, design settings
  source/media/...         original images / videos that the site actually uses
  source/fonts/*.woff2     webfonts (converted from OTF/TTF)
  source/data/*.csv        Personen / Orte databases used by the homepage archive

Needs: fontTools + brotli (only for the font conversion).
Usage: python3 tools/export_from_wordpress.py [path/to/wp-content]
"""
import glob
import json
import os
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / 'source'
DEFAULT_WP = ROOT.parent / 'SFU-old-emplice' / 'laragon daten' / 'sfu2' / 'wp-content'
WP = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_WP
UPLOADS = WP / 'uploads'
THEME = WP / 'themes' / 'semplice5'


# ---------------------------------------------------------------- wpress

def read_wpress(path, wanted):
    """Yield (name, bytes) for archive members whose path ends with one of `wanted`."""
    with open(path, 'rb') as f:
        while True:
            header = f.read(4377)
            if len(header) < 4377 or header == b'\0' * 4377:
                return
            name = header[:255].rstrip(b'\0').decode('utf-8', 'replace')
            size = int(header[255:269].rstrip(b'\0') or 0)
            prefix = header[281:].rstrip(b'\0').decode('utf-8', 'replace')
            full = os.path.join(prefix, name)
            if any(full == w or full.endswith('/' + w) for w in wanted):
                yield full, f.read(size)
            else:
                f.seek(size, 1)


# ---------------------------------------------------------------- sql

TOKEN = re.compile(r"\s*(\(|\)|,|;|'((?:[^'\\]|\\.)*)'|NULL|-?[\d.]+)", re.S)


def unescape_sql(s):
    return s.encode('utf-8').decode('unicode_escape').encode('latin1', 'replace').decode('utf-8', 'replace')


def table_rows(sql, table):
    rows = []
    for line in sql.split('\n'):
        if not line.startswith(f'INSERT INTO `SERVMASK_PREFIX_{table}`'):
            continue
        body = line[line.index('VALUES') + 6:]
        pos, row = 0, []
        while pos < len(body):
            m = TOKEN.match(body, pos)
            if not m:
                break
            pos = m.end()
            t = m.group(1)
            if t == '(':
                row = []
            elif t == ')':
                rows.append(row)
            elif t in (',', ';'):
                pass
            elif t.startswith("'"):
                row.append(unescape_sql(m.group(2)))
            elif t == 'NULL':
                row.append(None)
            else:
                row.append(t)
    return rows


POST_COLS = ['ID', 'post_author', 'post_date', 'post_date_gmt', 'post_content', 'post_title', 'post_excerpt',
             'post_status', 'comment_status', 'ping_status', 'post_password', 'post_name', 'to_ping', 'pinged',
             'post_modified', 'post_modified_gmt', 'post_content_filtered', 'post_parent', 'guid', 'menu_order',
             'post_type', 'post_mime_type', 'comment_count']


# ---------------------------------------------------------------- media references

UPLOAD_URL = re.compile(r'(?:https?://[^/"\')\s]+)?/wp-content/uploads/([^"\')\s?#]+)')


def collect_refs(content, ids, files):
    """Walk a Semplice content tree and record attachment ids / upload paths it uses."""
    if isinstance(content, dict):
        for key, value in content.items():
            if key in ('background-image', 'bg_video', 'bg_video_fallback', 'image') and isinstance(value, (str, int)) and str(value).isdigit():
                ids.add(str(value))
            collect_refs(value, ids, files)
        module = content.get('module')
        if module == 'image' and str(content.get('content', {}).get('xl', '')).isdigit():
            ids.add(str(content['content']['xl']))
        if module == 'gallerygrid':
            gallery = content.get('content', {}).get('xl') or {}
            for v in (gallery.values() if isinstance(gallery, dict) else gallery):
                ids.add(str(v))
    elif isinstance(content, list):
        for v in content:
            collect_refs(v, ids, files)
    elif isinstance(content, str):
        for m in UPLOAD_URL.finditer(content):
            files.add(m.group(1))


def main():
    backups = sorted(glob.glob(str(WP / 'ai1wm-backups' / '*.wpress')), key=os.path.getmtime)
    if not backups:
        sys.exit(f'no .wpress backup found in {WP}/ai1wm-backups')
    backup = backups[-1]
    print('backup:', backup)
    sql = next(data for _, data in read_wpress(backup, ['database.sql'])).decode('utf-8', 'replace')

    posts = {r[0]: dict(zip(POST_COLS, r)) for r in table_rows(sql, 'posts')}
    meta = {}
    for _mid, pid, key, value in table_rows(sql, 'postmeta'):
        meta.setdefault(pid, {})[key] = value
    options = {r[1]: r[2] for r in table_rows(sql, 'options')}

    def opt(name):
        try:
            return json.loads(options[name])
        except (KeyError, ValueError):
            return options.get(name)

    pages, footers = {}, {}
    for pid, p in posts.items():
        if p['post_status'] != 'publish' or p['post_type'] not in ('page', 'project', 'footer'):
            continue
        m = meta.get(pid, {})
        if not m.get('_semplice_content'):
            continue
        entry = {
            'id': pid,
            'type': p['post_type'],
            'slug': p['post_name'],
            'title': p['post_title'],
            'date': p['post_date'],
            'modified': p['post_modified'],
            'settings': json.loads(m['_semplice_post_settings']) if m.get('_semplice_post_settings') else {},
            'content': json.loads(m['_semplice_content']),
        }
        (footers if p['post_type'] == 'footer' else pages)[pid] = entry

    general = opt('semplice_settings_general')
    advanced = opt('semplice_customize_advanced')
    navigations = opt('semplice_customize_navigations')
    nav_ids = {navigations['default']}
    for p in pages.values():
        nav = p['settings'].get('meta', {}).get('navbar')
        if nav and nav != 'default':
            nav_ids.add(nav)
    used_footers = {advanced.get('global_footer')} | {p['settings'].get('meta', {}).get('footer') for p in pages.values()}
    footers = {k: v for k, v in footers.items() if k in used_footers}

    menu = []
    for pid, p in sorted(((k, v) for k, v in posts.items() if v['post_type'] == 'nav_menu_item' and v['post_status'] == 'publish'),
                         key=lambda kv: int(kv[1]['menu_order'])):
        menu.append({'title': p['post_title'], 'url': meta.get(pid, {}).get('_menu_item_url', '')})

    # which media does the site use?
    ids, files = set(), set()
    for entry in list(pages.values()) + list(footers.values()):
        collect_refs(entry['content'], ids, files)
        thumb = entry['settings'].get('thumbnail', {}).get('image')
        if thumb:
            ids.add(str(thumb))
    for nav_id in nav_ids:
        if navigations[nav_id].get('logo_img'):
            ids.add(str(navigations[nav_id]['logo_img']))
    collect_refs(advanced, ids, files)

    attachments = {}
    for aid in sorted(ids, key=int):
        p, m = posts.get(aid), meta.get(aid, {})
        if not p or not m.get('_wp_attached_file'):
            print('  missing attachment', aid)
            continue
        attachments[aid] = {
            'file': m['_wp_attached_file'],
            'alt': m.get('_wp_attachment_image_alt', ''),
            'caption': p['post_excerpt'],
            'title': p['post_title'],
            'mime': p['post_mime_type'],
        }
        files.add(m['_wp_attached_file'])

    content = {
        'site': {
            'title': general.get('site_title', options.get('blogname')),
            'tagline': general.get('site_tagline', options.get('blogdescription')),
            'home': general.get('page_on_front'),
            'project_slug': general.get('project_slug', 'artikel'),
            'old_hosts': ['http://sfu2.test', 'https://psychologie-im-nationalsozialismus.sfu.ac.at',
                          'http://psychologie-im-nationalsozialismus.sfu.ac.at', 'http://sfu.test'],
            'exported_from': os.path.basename(backup),
        },
        'menu': menu,
        'design': {
            'typography': opt('semplice_customize_typography'),
            'webfonts': opt('semplice_customize_webfonts'),
            'grid': opt('semplice_customize_grid'),
            'advanced': advanced,
            'navigations': {k: navigations[k] for k in nav_ids} | {'default': navigations['default']},
            'colors': opt('semplice_custom_colors'),
        },
        'pages': pages,
        'footers': footers,
        'attachments': attachments,
    }

    SOURCE.mkdir(exist_ok=True)

    # ---- data (Personen / Orte)
    data_dir = SOURCE / 'data'
    data_dir.mkdir(exist_ok=True)
    shutil.copy2(THEME / 'db' / 'sfu-datenbank-personen-3.csv', data_dir / 'personen.csv')
    shutil.copy2(THEME / 'db' / 'sfu-datenbank-orte1.csv', data_dir / 'orte.csv')
    import csv
    for row in csv.DictReader(open(data_dir / 'orte.csv', encoding='utf-8'), delimiter=';'):
        if row.get('imgSrc'):
            files.add('2021/11/' + row['imgSrc'])
    for row in csv.DictReader(open(data_dir / 'personen.csv', encoding='utf-8'), delimiter=';'):
        pass  # portraits are matched by file name in build.py; copy the whole set below
    for f in glob.glob(str(UPLOADS / '2021' / '11' / '*.png')):
        name = os.path.basename(f)
        if re.match(r'^(Thumbnail_)?\d\d_[^-]+\.png$', name):
            files.add('2021/11/' + name)
    files.update({'2022/01/na_thumb.png', '2022/01/na_portrait.png'})

    # ---- media
    media_dir = SOURCE / 'media'
    copied = 0
    for rel in sorted(files):
        rel = rel.replace('%20', ' ')
        src = UPLOADS / rel
        if not src.is_file():
            print('  missing upload', rel)
            continue
        dst = media_dir / rel
        if not dst.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            copied += 1
    for extra in ['images/rohracher3.jpg']:
        dst = media_dir / 'theme' / os.path.basename(extra)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(THEME / extra, dst)
    print(f'media: {len(files)} referenced, {copied} newly copied')

    # ---- fonts -> woff2
    from fontTools.ttLib import TTFont
    font_dir = SOURCE / 'fonts'
    font_dir.mkdir(exist_ok=True)
    srcs = {}
    for res in content['design']['webfonts'].get('ressources', {}).values():
        for family, url in re.findall(r"font-family:\s*'([^']+)';\s*src:\s*url\('([^']+)'\)", res.get('ressource-src', '')):
            srcs[family] = UPLOAD_URL.search(url).group(1)
    for family, rel in sorted(srcs.items()):
        dst = font_dir / f'{family}.woff2'
        if dst.exists():
            continue
        font = TTFont(UPLOADS / rel)
        font.flavor = 'woff2'
        font.save(dst)
    print('fonts:', len(srcs))
    content['design']['font_files'] = {family: f'{family}.woff2' for family in srcs}

    with open(SOURCE / 'content.json', 'w', encoding='utf-8') as f:
        json.dump(content, f, ensure_ascii=False, indent=1)
    print('pages:', len(pages), 'footers:', len(footers), 'attachments:', len(attachments))


if __name__ == '__main__':
    main()
