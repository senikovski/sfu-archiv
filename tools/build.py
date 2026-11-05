#!/usr/bin/env python3
"""
Static site builder for "Psychologie im Nationalsozialismus" (SFU).

Turns source/content.json (exported from the old Semplice/WordPress site) into
plain HTML/CSS in ./site. The page layout is rendered the same way Semplice
rendered it (sections > rows > columns > modules, with per-breakpoint CSS),
so the original design is kept without WordPress, jQuery or Semplice's
220 KB stylesheet.

Usage:  python3 tools/build.py            (needs Pillow for image conversion)
"""
import csv
import hashlib
import html
import json
import re
import shutil
import sys
import unicodedata
import urllib.parse
import urllib.request
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / 'source'
OUT = ROOT / 'site'

C = json.load(open(SRC / 'content.json', encoding='utf-8'))
SITE = C['site']
DESIGN = C['design']
ATTACH = C['attachments']
PAGES = C['pages']
HOME_ID = SITE['home']
NAV = DESIGN['navigations'][DESIGN['navigations']['default']]

BREAKPOINTS = {
    'lg': ' and (min-width: 992px) and (max-width: 1169.98px)',
    'md': ' and (min-width: 768px) and (max-width: 991.98px)',
    'sm': ' and (min-width: 544px) and (max-width: 767.98px)',
    'xs': ' and (max-width: 543.98px)',
}
GRID_WIDTH = max(1170, DESIGN['grid'].get('width', 1170))


# =====================================================================
# URLs
# =====================================================================

def page_path(pid):
    """Site-relative directory of a page ('' for the homepage)."""
    pid = str(pid)
    if pid == HOME_ID:
        return ''
    p = PAGES[pid]
    if p['type'] == 'project':
        return f"{SITE['project_slug']}/{p['slug']}/"
    return f"{p['slug']}/"


SLUGS = {p['slug']: pid for pid, p in PAGES.items()}
OLD_HOST = '|'.join(re.escape(h) for h in SITE['old_hosts'])
OLD_URL = re.compile(rf'(?:{OLD_HOST})(/[^"\'\s)<>]*)?')


class Page:
    """Per-page render state: relative prefix, collected CSS, unique counters."""

    def __init__(self, pid, path):
        self.pid = pid
        self.path = path
        self.prefix = '../' * path.count('/')
        self.css = []
        self.motion_css = []
        self.motion_css_enabled = False
        self.counter = 0

    def url(self, site_path):
        return (self.prefix + site_path) or './'

    def page_url(self, pid, hash_=''):
        pid = str(pid)
        if pid not in PAGES:
            pid = HOME_ID
        target = page_path(pid)
        if target == self.path and hash_:
            return hash_
        return self.url(target) + hash_

    def rewrite_old_url(self, m):
        path = (m.group(1) or '/').split('#')[0]
        hash_ = '#' + m.group(1).split('#', 1)[1] if m.group(1) and '#' in m.group(1) else ''
        if path.startswith('/wp-content/uploads/'):
            rel = html.unescape(path[len('/wp-content/uploads/'):]).replace('%20', ' ')
            return self.url(media(rel)) if media_exists(rel) else m.group(0)
        slug = path.strip('/').split('/')[-1]
        if path.strip('/') == '':
            return self.page_url(HOME_ID, hash_)
        if slug in SLUGS:
            return self.page_url(SLUGS[slug], hash_)
        return m.group(0)

    def rewrite(self, text):
        return OLD_URL.sub(self.rewrite_old_url, text)

    def uid(self, prefix='t'):
        self.counter += 1
        return f'{prefix}{self.counter}'


# =====================================================================
# media (images -> webp, other files copied)
# =====================================================================

IMG_EXT = {'.jpg', '.jpeg', '.png', '.webp'}
_size_cache = {}


def image_size(rel):
    rel = nfc(rel)
    if rel not in _size_cache:
        with Image.open(SRC / 'media' / rel) as im:
            _size_cache[rel] = im.size
    return _size_cache[rel]


def nfc(rel):
    return unicodedata.normalize('NFC', rel)


def safe_name(rel):
    """ASCII-only output path (umlauts in file names break on some servers)."""
    rel = unicodedata.normalize('NFKD', rel).encode('ascii', 'ignore').decode()
    return re.sub(r'[^A-Za-z0-9._/-]+', '-', rel)


def media_exists(rel):
    return (SRC / 'media' / nfc(rel)).is_file()


def media(rel, width=None):
    """Return the site-relative URL of a media file, converting images to webp."""
    rel = nfc(rel)
    src = SRC / 'media' / rel
    ext = src.suffix.lower()
    if ext not in IMG_EXT:
        out_rel = f'media/{safe_name(rel)}'
        dst = OUT / out_rel
        if not dst.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        return out_rel
    w, h = image_size(rel)
    width = min(width or 1920, w)
    stem = safe_name(str(Path(rel).with_suffix('')))
    out_rel = f'media/{stem}-{width}.webp'
    dst = OUT / out_rel
    if not dst.exists():
        dst.parent.mkdir(parents=True, exist_ok=True)
        with Image.open(src) as im:
            if im.mode in ('P', 'LA') or (im.mode == 'RGBA' and ext != '.png'):
                im = im.convert('RGBA')
            elif im.mode not in ('RGB', 'RGBA', 'L'):
                im = im.convert('RGB')
            if width < w:
                im = im.resize((width, round(h * width / w)), Image.LANCZOS)
            im.save(dst, 'WEBP', quality=80, method=5)
    return out_rel


def srcset(rel, page, max_width):
    """(src, srcset, width, height) for an <img>."""
    w, h = image_size(rel)
    steps = sorted({min(w, s) for s in (480, 960, 1600, 2400) if s <= max(max_width * 2, 480)} | {min(w, max_width)})
    entries = [f'{page.url(media(rel, s))} {s}w' for s in steps]
    return page.url(media(rel, min(w, max_width))), ', '.join(entries), w, h


def attachment_file(aid):
    a = ATTACH.get(str(aid))
    if not a or not media_exists(a['file']):
        return None
    return nfc(a['file'])


def bg_image_url(aid, page, width=1920):
    rel = attachment_file(aid)
    return page.url(media(rel, width)) if rel else None


# =====================================================================
# Semplice style -> CSS (port of admin/editor/module.php)
# =====================================================================

def get_border(styles):
    css = ''
    for prop in ('border-width', 'border-style', 'border-radius', 'border-color'):
        if prop in styles:
            css += f'{prop}:{styles[prop]};'
    return css


def get_bg_css(styles, page, full=True):
    css = ''
    image = styles.get('background-image')
    if image and styles.get('background_type') != 'vid':
        url = bg_image_url(image, page)
        if url:
            css += f'background-image:url({url});'
    if image and full:
        if styles.get('background-repeat'):
            css += f"background-repeat:{styles['background-repeat']};"
        if styles.get('background-size') in ('cover', 'contain'):
            css += f"background-size:{styles['background-size']};"
        elif styles.get('background-repeat') and styles['background-repeat'] != 'no-repeat':
            css += 'background-size:auto;'
        css += f"background-position:{styles.get('background-position') or 'top left'};"
        css += f"background-attachment:{styles.get('background-attachment') or 'scroll'};"
    elif image and styles.get('background-position'):
        css += f"background-position:{styles['background-position']};"
    if full and styles.get('background-color'):
        color = styles['background-color']
        css += f"background-color:{color if re.match(r'^#[0-9a-f]{6}$', color, re.I) else 'transparent'};"
    return css


def container_styles(mode, styles, id_, module, bp, page):
    if mode == 'container':
        sel = f'#{id_} .container'
    elif mode == 'cover':
        sel = f'#{id_} .cover-image'
    else:
        sel = f'#{id_}'
    css = ''
    if mode != 'branding':
        for d in ('top', 'right', 'bottom', 'left'):
            for prop in (f'padding-{d}', f'margin-{d}'):
                if prop in styles:
                    css += f'{prop}:{styles[prop]};'
    if mode != 'content':
        css += get_border(styles)
    css += get_bg_css(styles, page, full=(bp == 'xl'))
    for prop in ('height', 'opacity', 'z-index'):
        if prop in styles:
            css += f'{prop}:{styles[prop]};'
    if mode == 'section' and 'mix-blend-mode' in styles:
        css += f"mix-blend-mode:{styles['mix-blend-mode']};"
    if 'order' in styles:
        css += f"order:{styles['order']};"
    out = f'{sel}{{{css}}}' if css else ''
    if mode == 'content':
        inner = ''
        if styles.get('box-shadow') and module != 'paragraph':
            inner += f"box-shadow:{styles['box-shadow']};"
        elif styles.get('text-shadow') and module in ('paragraph', 'text') and '0rem 0rem 0rem' not in styles['text-shadow']:
            inner += f"text-shadow:{styles['text-shadow']};"
        if module != 'button':
            inner += get_border(styles)
        if inner:
            out += f'#content-holder #{id_} .is-content{{{inner}}}'
    return out


def generate_css(mode, css_by_bp, id_, module, page):
    out = ''
    if css_by_bp.get('xl'):
        rule = container_styles(mode, css_by_bp['xl'], id_, module, 'xl', page)
        if rule:
            out += '#content-holder ' + rule
    for bp, query in BREAKPOINTS.items():
        if css_by_bp.get(bp):
            rule = container_styles(mode, css_by_bp[bp], id_, module, bp, page)
            if rule:
                out += f'@media screen{query}{{#content-holder {rule}}}'
    return out


def attrs(values):
    return ''.join(f' {k}="{html.escape(str(v))}"' for k, v in values.items() if not isinstance(v, (dict, list)))


# =====================================================================
# text cleanup: TinyMCE leftovers + Semplice's responsive text sizes
# =====================================================================

TAG = re.compile(r'<([a-zA-Z][a-zA-Z0-9]*)((?:\s+[^\s=>]+(?:="[^"]*")?)*)\s*(/?)>')
ATTR = re.compile(r'([^\s=]+)(?:="([^"]*)")?')
SIZING = ('font-size', 'line-height', 'letter-spacing')


def parse_style(style):
    out = {}
    for part in style.split(';'):
        if ':' in part:
            k, v = part.split(':', 1)
            out[k.strip().lower()] = v.strip()
    return out


def clean_text_html(content, page, sizing=True):
    """Drop TinyMCE attributes; turn inline/responsive font sizes into page CSS.

    Semplice's frontend JS (applyTextSizings) gives every element inside a text
    module the value of data-<prop>-<breakpoint>, falling back to data-<prop>-xl,
    and otherwise removes the inline value. That is reproduced here with
    generated classes so no JavaScript is needed.
    """
    content = re.sub(r'<br data-mce-bogus="1"\s*/?>', '', content)

    def fix(m):
        tag, raw, close = m.group(1), m.group(2), m.group(3)
        a = {}
        for am in ATTR.finditer(raw):
            a[am.group(1)] = am.group(2) if am.group(2) is not None else ''
        sizes = {}
        for key in list(a):
            if key.startswith('data-mce-'):
                del a[key]
                continue
            sm = re.match(r'data-(font-size|line-height|letter-spacing)-(xl|lg|md|sm|xs)$', key)
            if sm:
                sizes.setdefault(sm.group(2), {})[sm.group(1)] = a.pop(key)
        if sizing:
            style = parse_style(a.get('style', ''))
            for prop in SIZING:
                style.pop(prop, None)
            if style:
                a['style'] = ';'.join(f'{k}: {v}' for k, v in style.items()) + ';'
            else:
                a.pop('style', None)
            if sizes:
                cls = page.uid('t')
                a['class'] = (a.get('class', '') + ' ' + cls).strip()
                base = ''.join(f'{p}:{v};' for p, v in sizes.get('xl', {}).items())
                if base:
                    page.css.append(f'#content-holder .{cls}{{{base}}}')
                for bp, query in BREAKPOINTS.items():
                    if sizes.get(bp):
                        rule = ''.join(f'{p}:{v};' for p, v in sizes[bp].items())
                        page.css.append(f'@media screen{query}{{#content-holder .{cls}{{{rule}}}}}')
        return f'<{tag}' + ''.join(f' {k}' if v == '' and k in ('async', 'defer') else f' {k}="{v}"' for k, v in a.items()) + (' /' if close else '') + '>'

    content = TAG.sub(fix, content)
    return page.rewrite(content)


def clean_code(content, page):
    """Code modules: drop Leaflet/PapaParse includes (handled by archiv.js) and empty blocks."""
    content = re.sub(r'<script[^>]*src="[^"]*(leaflet|papaparse)[^"]*"[^>]*>\s*</script>', '', content)

    def empty(m):
        body = re.sub(r'//[^\n]*|/\*.*?\*/', '', m.group(2), flags=re.S).strip()
        return '' if not body else m.group(0)

    content = re.sub(r'<(script|style)>(.*?)</\1>', empty, content, flags=re.S)
    content = content.replace('<img id="portrait" src="">', '<div id="portrait" role="img"></div>')
    return page.rewrite(content)


# =====================================================================
# modules (port of admin/editor/modules/*.php)
# =====================================================================

def link_href(opts, page, prefix='link'):
    kind = opts.get(f'{prefix}_type', 'url')
    if kind in ('url', 'email'):
        url = opts.get(prefix if prefix == 'link' else f'{prefix}', '') or ''
        if re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', url):
            return 'mailto:' + url
        return page.rewrite(url)
    target = opts.get(f'{prefix}_{kind}')
    return page.page_url(target) if target else page.page_url(HOME_ID)


def module_text(m, cid, page, ctx):
    content = m['content']['xl']
    if content == 'default':
        content = ''
    return f'<div class="is-content">{clean_text_html(content, page)}</div>'


def module_image(m, cid, page, ctx):
    o = m.get('options', {})
    aid = m['content']['xl']
    rel = attachment_file(aid)
    if not rel:
        return ''
    a = ATTACH[str(aid)]
    display = round(GRID_WIDTH * ctx['col_width'] / 12)
    alt = html.escape(a.get('alt') or a.get('title') or '')
    if rel.lower().endswith('.svg'):
        tag = f'<img class="is-content" src="{page.url(media(rel))}" alt="{alt}" data-width="{o.get("width", "original")}">'
    else:
        src, sset, w, h = srcset(rel, page, display if o.get('width') == 'grid-width' else min(display, image_size(rel)[0]))
        lazy = '' if ctx['first'] else ' loading="lazy"'
        tag = (f'<img class="is-content" src="{src}" srcset="{sset}" sizes="(max-width: 767px) 100vw, {display}px" '
               f'width="{w}" height="{h}" alt="{alt}" data-width="{o.get("width", "original")}" decoding="async"{lazy}>')
    if o.get('image_link_type', 'url') == 'url' and o.get('image_link'):
        tag = f'<a href="{page.rewrite(o["image_link"])}" target="{o.get("image_link_target", "_blank")}">{tag}</a>'
    elif o.get('image_link_type', 'url') != 'url' and o.get('image_link_' + o['image_link_type']):
        tag = f'<a href="{page.page_url(o["image_link_" + o["image_link_type"]])}">{tag}</a>'
    return f'<div class="ce-image" data-align="{o.get("align", "left")}">{tag}</div>'


def module_button(m, cid, page, ctx):
    o = m.get('options', {})
    label = m['content']['xl'] or o.get('label') or 'Semplice Button'
    parent_props = ('background-color', 'border-width', 'border-radius', 'border-color')
    child_props = ('font-size', 'color', 'letter-spacing', 'border-radius', 'padding-bottom', 'padding-left', 'padding-right', 'padding-top')
    normal = {'parent': '', 'child': ''}
    hover = {'parent': '', 'child': ''}
    for kind, props in (('parent', parent_props), ('child', child_props)):
        for attr_, value in o.items():
            if attr_ in props:
                normal[kind] += f'{attr_}:{value};'
                if attr_ == 'letter-spacing':
                    normal[kind] += f"margin-right:{value[1:] if value.startswith('-') else '-' + value};"
            elif ('hover' in attr_ and attr_.replace('hover-', '') in props) or attr_ == 'color':
                hover[kind] += f"{attr_.replace('hover-', '')}:{value} !important;"
                if attr_ == 'hover-letter-spacing' and kind == 'child':
                    hover[kind] += f"margin-right:{value[1:] if value.startswith('-') else '-' + value};"
    sel = f'#content-holder #{cid} .is-content'
    page.css.append(f'{sel}{{{normal["parent"]}}}{sel}:hover{{{hover["parent"]}}}{sel} a{{{normal["child"]}}}{sel}:hover a{{{hover["child"]}}}')
    href = link_href(o, page)
    target = '_self' if o.get('link_target') == 'same' else '_blank'
    rel = '' if target == '_self' else ' rel="noopener"'
    font = f' data-font="{o["font_family"]}"' if o.get('font_family') else ''
    return (f'<div class="ce-button" data-align="{o.get("align", "center")}"><div class="is-content" data-width="{o.get("width", "auto")}">'
            f'<a{font} href="{href}" target="{target}"{rel}>{html.escape(label, quote=False)}</a></div></div>')


def module_spacer(m, cid, page, ctx):
    o = m.get('options', {})
    if 'background-color' in o:
        page.css.append(f'#content-holder #{cid} .spacer{{background-color:{o["background-color"]};}}')
    if 'height' in o:
        page.css.append(f'#content-holder #{cid} .spacer{{height:{o["height"]};}}')
    return '<div class="spacer-container"><div class="is-content"><div class="spacer"></div></div></div>'


def module_code(m, cid, page, ctx):
    return f'<div class="is-content ce-code">{clean_code(m["content"]["xl"], page)}</div>'


def module_gallerygrid(m, cid, page, ctx):
    o = m.get('options', {})
    col = int(o.get('col', 4))
    gutter = int(o.get('hor_gutter', 30))
    vgutter = int(o.get('ver_gutter', 30))
    images = m['content']['xl']
    images = images.values() if isinstance(images, dict) else images
    items = ''
    for aid in images:
        rel = attachment_file(aid)
        if not rel:
            continue
        w, h = image_size(rel)
        alt = html.escape(ATTACH[str(aid)].get('alt') or ATTACH[str(aid)].get('title') or '')
        items += (f'<div class="masonry-item" data-xl-width="{col}" data-sm-width="6" data-xs-width="12">'
                  f'<img src="{page.url(media(rel, 600))}" width="{w}" height="{h}" alt="{alt}" loading="lazy"></div>')
    page.css.append(f'#content-holder #{cid} .masonry{{margin:0 -{gutter / 2}px}}#content-holder #{cid} .masonry-item{{padding:0 {gutter / 2}px {vgutter}px}}')
    return f'<div class="masonry">{items}</div>'


MODULES = {
    'text': module_text, 'image': module_image, 'button': module_button,
    'spacer': module_spacer, 'code': module_code, 'gallerygrid': module_gallerygrid,
}


# =====================================================================
# sections / rows / columns
# =====================================================================

def has_hover_motion(item):
    return item.get('motions', {}).get('event') == 'on_hover' and bool(item['motions'].get('timeline'))


def motion_initial_css(id_, item):
    """Initial state of a Semplice motion (port of animate.php get_motion_css, regular props only).

    Semplice only prints this CSS on pages with scroll-reveal disabled; it overrides
    the column's own styles (e.g. the 0.75 opacity of .article-cards columns)."""
    initial = item.get('motions', {}).get('initial', {})
    css = ''
    for prop in ('background-color', 'border-color', 'border-width', 'opacity'):
        if prop in initial and not (prop == 'background-color' and 'module' in item):
            css += f'{prop}:{initial[prop]};'
    if initial.get('color') and initial['color'] != 'transparent':
        css += f"color:{initial['color']};"
    return f'#content-holder #{id_}{{{css}}}' if css else ''


def background_video(styles, page):
    vid = attachment_file(styles.get('bg_video')) if styles.get('bg_video') else None
    if not vid:
        return '<div class="background-video"></div>'
    kind = 'video/webm' if vid.endswith('.webm') else 'video/mp4'
    return (f'<div class="background-video"><video autoplay muted loop playsinline preload="auto">'
            f'<source src="{page.url(media(vid))}" type="{kind}"></video></div>')


def prepare_captions(ram):
    """Image captions sit in their own column next to the image, centred in it, so
    they ended up far from the picture. Mark caption columns so the text is set
    flush against the image edge, and push the image toward its caption."""
    def plain(t):
        return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', t))).strip()
    for sid, section in ram['order'].items():
        if sid not in ram:
            continue
        rows = {'r': section} if 'columns' in section else section
        for row in rows.values():
            cols = [(c, its) for c, its in row['columns'].items() if c in ram]
            for k, (col, items) in enumerate(cols):
                mods = [ram[i] for i in items if i in ram]
                if not mods or not {m['module'] for m in mods} <= {'image', 'spacer'} or not any(m['module'] == 'image' for m in mods):
                    continue
                for side, j in (('left', k - 1), ('right', k + 1)):
                    if not 0 <= j < len(cols):
                        continue
                    ccol, citems = cols[j]
                    cmods = [ram[i] for i in citems if i in ram]
                    texts = [m for m in cmods if m['module'] == 'text']
                    if not texts or any(m['module'] not in ('text', 'spacer') for m in cmods):
                        continue
                    if len(' '.join(plain(m['content']['xl']) for m in texts)) >= 260:
                        continue
                    ram[ccol]['classes'] = ((ram[ccol].get('classes') or '') + f' img-caption caption-{side}').strip()
                    ram[col]['classes'] = ((ram[col].get('classes') or '') + f' captioned-{side}').strip()
                    for m in mods:
                        if m['module'] == 'image':
                            m.setdefault('options', {})['align'] = 'left' if side == 'left' else 'right'


def collapsible_pairs(ram, items):
    """Bibliographie boxes: a header text module ("BIBLIOGRAPHIE", class autorBox)
    followed by the list (class bodenBox). site.js turns the header into a toggle."""
    out = {}
    for a, b in zip(items, items[1:]):
        ma, mb = ram.get(a, {}), ram.get(b, {})
        if ma.get('module') == 'text' and mb.get('module') == 'text' and 'bodenBox' in (mb.get('classes') or ''):
            label = re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', ma['content']['xl']))).strip()
            if label.upper() == 'BIBLIOGRAPHIE':
                out[a] = f' data-collapse-toggle="{b}"'
                out[b] = ' data-collapse-body'
    return out


def render_column(ram, column_id, items, page, ctx, extra=''):
    col = ram[column_id]
    page.css.append(generate_css('column', col.get('styles', {}), column_id, False, page))
    classes = 'column'
    if col.get('classes'):
        classes += ' ' + col['classes']
    if col.get('type') == 'spacer':
        classes += ' spacer-column'
    if has_hover_motion(col):
        classes += ' hover-lift'
        if page.motion_css_enabled:
            page.motion_css.append(motion_initial_css(column_id, col))
    width_attrs = {f'data-{bp}-width': v for bp, v in col.get('width', {}).items() if bp}
    styles = col.get('styles', {}).get('xl', {})
    bg = ''
    if styles.get('background_type') == 'vid':
        page.css.append(f"#content-holder #{column_id} > .background-video{{{get_bg_css(styles, page)}}}")
        bg = background_video(styles, page)
    ctx = dict(ctx, col_width=int(col.get('width', {}).get('xl', 12) or 12))
    body = ''
    extra_attrs = collapsible_pairs(ram, items)
    for cid in items:
        if cid not in ram or ram[cid].get('module') not in MODULES:
            continue
        m = ram[cid]
        inner = MODULES[m['module']](m, cid, page, ctx)
        page.css.append(generate_css('content', m.get('styles', {}), cid, m['module'], page))
        classes_m = 'column-content' + (' ' + m['classes'] if m.get('classes') else '')
        body += f'<div id="{cid}" class="{classes_m}" data-module="{m["module"]}"{extra_attrs.get(cid, "")}>{inner}</div>'
        ctx['first'] = False
    extra += HOOKS.get((page.pid, column_id), lambda p: '')(page)
    return (f'<div id="{column_id}" class="{classes}"{attrs(width_attrs)}{attrs(col.get("layout", {}))}>'
            f'{bg}<div class="content-wrapper">{body}</div>{extra}</div>')


def render_rows(ram, section, page, ctx):
    rows = {section.get('row_id', 'row'): {'columns': section['columns']}} if 'columns' in section else section
    out = ''
    for row_id, row in rows.items():
        cols = ''.join(render_column(ram, cid, items, page, ctx) for cid, items in row['columns'].items() if cid in ram)
        out += f'<div id="{row_id}" class="row">{cols}</div>'
    return out


def render_sections(ram, page, is_footer=False):
    html_out = ''
    cover_visible = ram.get('cover_visibility', 'hidden') == 'visible'
    first = True
    for section_id, section in ram['order'].items():
        if section_id not in ram:
            continue
        if section_id == 'cover' and (is_footer or not cover_visible):
            continue
        s = ram[section_id]
        styles = s.get('styles', {}).get('xl', {})
        layout = dict(s.get('layout', {}))
        css_classes = 'content-block' + (' ' + s['classes'] if s.get('classes') else '')
        element_id = section_id
        if layout.get('data-height') == 'custom':
            page.css.append(generate_css('container', s.get('customHeight', {}), section_id, False, page))
        if s.get('options', {}).get('desktop_visibility') == 'hidden':
            page.css.append(f'@media screen and (min-width: 1170px){{#{section_id}{{display:none !important}}}}')
        ctx = {'first': first, 'col_width': 12}
        content = f'<div class="container">{render_rows(ram, section, page, ctx)}</div>'
        prepend = ''
        if section_id == 'cover':
            element_id = f'cover-{page.pid}'
            css_classes = 'semplice-cover'
            layout['data-cover'] = 'visible'
            if styles.get('arrow_visibility', 'visible') != 'hidden':
                prepend += ('<a class="show-more" href="#content-start" aria-label="Weiter"><svg width="53" height="20" viewBox="0 0 53 20">'
                            '<polygon points="26.5,17.688 9.114,3.779 10.303,2.312 26.5,15.269 42.697,2.313 43.886,3.779"/></svg></a>')
                if styles.get('arrow_color'):
                    page.css.append(f"#content-holder .semplice-cover .show-more svg{{fill:{styles['arrow_color']}}}")
        if styles.get('background_type') == 'vid':
            target = f'{element_id} .semplice-cover-inner' if section_id == 'cover' else element_id
            page.css.append(f"#content-holder #{target} > .background-video{{{get_bg_css(styles, page)}}}")
            prepend += background_video(styles, page)
        elif section_id == 'cover':
            prepend += '<div class="cover-image-wrapper"><div class="cover-image"></div></div>'
            page.css.append(generate_css('cover', s.get('styles', {}), element_id, False, page))
        content = prepend + content
        if section_id == 'cover':
            content = f'<div class="semplice-cover-inner">{content}</div>'
        else:
            page.css.append(generate_css('section', s.get('styles', {}), section_id, False, page))
        html_out += f'<section id="{element_id}" class="{css_classes}"{attrs(layout)}>{content}</section>'
        if section_id == 'cover':
            html_out += '<div id="content-start"></div>'
        first = False
    return html_out


# =====================================================================
# page-specific additions that custom.js used to do in the browser
# =====================================================================

def hook_autoren(page):
    """Move the 'Die Autoren' box into the 'Über das Archiv' column (was done by custom.js)."""
    return AUTOREN.pop(page.pid, '')


def hook_dreier(page):
    img = page.url(media('theme/rohracher3.jpg', 900))
    return '<div id="dreierWrap">' + ''.join(f'<img class="dreierBG" src="{img}" alt="" loading="lazy">' for _ in range(3)) + '</div>'


AUTOREN = {}
HOOKS = {
    (HOME_ID, 'column_0d12d0689'): hook_autoren,
    (HOME_ID, 'column_b94503af2'): hook_dreier,
}


def prepare_home(ram):
    """Pull #autoren out of its code module so it can be placed into its column."""
    for key, m in ram.items():
        if isinstance(m, dict) and m.get('module') == 'code' and 'id="autoren"' in m['content']['xl']:
            code = m['content']['xl']
            match = re.search(r'<div id="autoren">.*?</div>', code, re.S)
            AUTOREN[HOME_ID] = match.group(0)
            m['content']['xl'] = code.replace(match.group(0), '')


# =====================================================================
# Personen / Orte archive (static markup + data for archiv.js)
# =====================================================================

UMLAUTE = {'Ü': 'Ue', 'Ä': 'Ae', 'Ö': 'Oe', 'ü': 'ue', 'ä': 'ae', 'ö': 'oe', 'ß': 'ss'}
ZIFFERN_OUTLINE = [chr(0x2460 + i) for i in range(20)]
ZIFFERN_FILLED = [chr(0x2776 + i) for i in range(10)] + [chr(0x24EB + i) for i in range(10)]


def replace_umlaute(s):
    return ''.join(UMLAUTE.get(ch, ch) for ch in s)


def article_link(href, title):
    """Resolve the article references of the CSV files to page ids."""
    href = (href or '').strip().strip('/')
    slug = href.split('/')[-1]
    if slug in SLUGS:
        return SLUGS[slug]
    words = [w.lower() for w in re.findall(r'\w{5,}', title or '')]
    for pid, p in PAGES.items():
        if p['type'] == 'project' and words and all(w in p['slug'].lower() or w in p['title'].lower() for w in words[-1:]):
            return pid
    return None


def read_csv(name):
    rows = list(csv.DictReader(open(SRC / 'data' / name, encoding='utf-8'), delimiter=';'))
    return [r for r in rows if any((v or '').strip() for v in r.values())]


def split_list(s):
    return [x.strip() for x in (s or '').split('.') if x.strip()]


def articles_of(row, count, page):
    out = []
    for i in range(1, count + 1):
        title = (row.get(f'Artikel{i}') or '').strip()
        if len(title) <= 3:
            continue
        pid = article_link(row.get(f'artikel{i}Href'), title)
        out.append({'title': title, 'author': (row.get(f'Autor{i}') or '').strip(), 'href': page.page_url(pid) if pid else ''})
    return out


# ---- archive sources: Sanity (default when source/sanity.json exists) or the CSV files

SANITY_CONFIG = SRC / 'sanity.json'
USE_CSV = '--csv' in sys.argv

PERSON_QUERY = """*[_type == "person" && !(_id in path("drafts.**"))] | order(coalesce(reihenfolge, 100000) asc, name asc) {
  name, jahre, text,
  "portrait": portrait.asset->{_id, url, extension},
  "thumbnail": thumbnail.asset->{_id, url, extension},
  "artikel": artikel[]->{titel, autor, seite},
  "personen": personen[]->name, "orte": orte[]->name, weitereOrte
}"""
ORT_QUERY = """*[_type == "ort" && !(_id in path("drafts.**"))] | order(coalesce(reihenfolge, 100000) asc, name asc) {
  name, text, adresse, lage, "bild": bild.asset->{_id, url, extension},
  "artikel": artikel[]->{titel, autor, seite}, "personen": personen[]->name
}"""


def _ssl_context():
    """python.org builds on macOS ship without root certificates; use certifi if present."""
    import ssl
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


SSL = _ssl_context()


def sanity_query(cfg, query):
    url = (f"https://{cfg['projectId']}.apicdn.sanity.io/v{cfg.get('apiVersion', '2024-01-01')}/data/query/"
           f"{cfg['dataset']}?query={urllib.parse.quote(query)}")
    with urllib.request.urlopen(url, timeout=60, context=SSL) as r:
        return json.load(r)['result']


def sanity_image(asset):
    """Download a Sanity image once (into source/media/sanity/, not committed) and return its media path."""
    if not asset:
        return None
    rel = f"sanity/{asset['_id']}.{asset.get('extension', 'jpg')}"
    dst = SRC / 'media' / rel
    if not dst.exists():
        dst.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(asset['url'], timeout=120, context=SSL) as r:
            dst.write_bytes(r.read())
    return rel


def load_archive():
    """Personen/Orte as plain dicts: {name, jahr, text, portrait, thumb, artikel[(title, author, pid)], personen, orte}."""
    if SANITY_CONFIG.exists() and not USE_CSV:
        cfg = json.loads(SANITY_CONFIG.read_text(encoding='utf-8'))
        def arts(items):
            return [((a.get('titel') or '').strip(), (a.get('autor') or '').strip(), SLUGS.get(a.get('seite') or ''))
                    for a in (items or []) if a and (a.get('titel') or '').strip()]
        personen = [{
            'name': (p.get('name') or '').strip(), 'jahr': (p.get('jahre') or '').strip(), 'text': (p.get('text') or '').strip(),
            'portrait': sanity_image(p.get('portrait')), 'thumb': sanity_image(p.get('thumbnail')),
            'artikel': arts(p.get('artikel')),
            'personen': [n for n in (p.get('personen') or []) if n],
            'orte': [n for n in (p.get('orte') or []) if n] + (p.get('weitereOrte') or []),
        } for p in sanity_query(cfg, PERSON_QUERY) if p.get('name')]
        orte = [{
            'name': (o.get('name') or '').strip(), 'text': (o.get('text') or '').strip(),
            'lat': o['lage']['lat'], 'lng': o['lage']['lng'], 'img': sanity_image(o.get('bild')),
            'artikel': arts(o.get('artikel')), 'personen': [n for n in (o.get('personen') or []) if n],
        } for o in sanity_query(cfg, ORT_QUERY) if o.get('name') and (o.get('lage') or {}).get('lat') is not None]
        print(f'  archive: Sanity project {cfg["projectId"]} ({len(personen)} Personen, {len(orte)} Orte)')
        return personen, orte

    def arts(row, count):
        out = []
        for i in range(1, count + 1):
            title = (row.get(f'Artikel{i}') or '').strip()
            if len(title) > 3:
                out.append((title, (row.get(f'Autor{i}') or '').strip(), article_link(row.get(f'artikel{i}Href'), title)))
        return out
    personen = []
    for i, row in enumerate(read_csv('personen.csv')):
        name = row['Name'].strip()
        file_name = f"{i:02d}_{replace_umlaute(name.replace(' ', '_'))}.png"
        thumb, portrait = f'2021/11/Thumbnail_{file_name}', f'2021/11/{file_name}'
        personen.append({
            'name': name, 'jahr': row['Jahr'].strip(), 'text': row['Text'].strip(),
            'portrait': portrait if media_exists(portrait) else None, 'thumb': thumb if media_exists(thumb) else None,
            'artikel': arts(row, 4), 'personen': split_list(row['Personen']), 'orte': split_list(row['Orte']),
        })
    orte = []
    for row in read_csv('orte.csv'):
        img = '2021/11/' + row['imgSrc']
        orte.append({
            'name': row['Ort'].strip(), 'text': row['Text'].strip(),
            # the CSV columns "Long"/"Lat" are swapped: "Long" holds the latitude
            'lat': float(row['Long']), 'lng': float(row['Lat']), 'img': img if media_exists(img) else None,
            'artikel': arts(row, 15), 'personen': split_list(row['Personen']),
        })
    print(f'  archive: CSV files ({len(personen)} Personen, {len(orte)} Orte)')
    return personen, orte


ARCHIVE = None


def archive_data(page):
    global ARCHIVE
    if ARCHIVE is None:
        ARCHIVE = load_archive()
    src_personen, src_orte = ARCHIVE
    links = lambda items: [{'title': t, 'author': a, 'href': page.page_url(pid) if pid else ''} for t, a, pid in items]
    personen = [{
        'name': p['name'], 'jahr': p['jahr'], 'text': p['text'],
        # no thumbnail of its own: use the portrait (cropped by CSS), else the placeholder
        'thumb': page.url(media(p['thumb'] or p['portrait'] or '2022/01/na_thumb.png', 120 if p['thumb'] else 240)),
        'thumbMissing': not (p['thumb'] or p['portrait']),
        'thumbCover': not p['thumb'],
        'portrait': page.url(media(p['portrait'] or '2022/01/na_portrait.png', 900)),
        'artikel': links(p['artikel']), 'personen': p['personen'], 'orte': p['orte'],
    } for p in src_personen]
    orte = [{
        'name': o['name'], 'text': o['text'], 'lat': o['lat'], 'lng': o['lng'],
        'img': page.url(media(o['img'], 1000)) if o['img'] else '',
        'thumb': page.url(media(o['img'], 240)) if o['img'] else '',
        'artikel': links(o['artikel']), 'personen': o['personen'],
    } for o in src_orte]
    return {'personen': personen, 'orte': orte}


def update_counters(ram):
    """Homepage buttons "32 Personen" / "12 Orte" follow the database."""
    personen, orte = ARCHIVE or load_archive()
    for m in ram.values():
        if isinstance(m, dict) and m.get('module') == 'button':
            label = m.get('options', {}).get('label') or ''
            if re.fullmatch(r'\d+ Personen', label):
                m['options']['label'] = f'{len(personen)} Personen'
            elif re.fullmatch(r'\d+ Orte', label):
                m['options']['label'] = f'{len(orte)} Orte'


def esc(s):
    return html.escape(s, quote=False)


def render_archive(page, code_html):
    """Fill the empty containers of the Personen/Orte code modules with initial content."""
    data = archive_data(page)
    personen, orte = data['personen'], data['orte']
    liste = ''.join(
        f'<div class="listenElement" data-index="{i}"><div class="thumbnail{" missingImg" if p["thumbMissing"] else ""}" '
        f'style="background-image:url({p["thumb"]}){";background-size:cover" if p["thumbCover"] else ""}"></div><h2>{esc(p["name"])}</h2><h3>{esc(p["jahr"])}</h3></div>'
        for i, p in enumerate(personen))
    code_html = code_html.replace('<div id="personenListe"></div>', f'<div id="personenListe">{liste}</div>')
    ortliste = ''.join(
        f'<div class="ortElement" data-index="{i}"><h5 class="nummerOrt">{ZIFFERN_OUTLINE[i]}</h5><h4 class="ortName">{esc(o["name"])}</h4></div>'
        for i, o in enumerate(orte))
    code_html = code_html.replace('<div id="orteliste"></div>', f'<div id="orteliste">{ortliste}</div>')
    return code_html, data


# =====================================================================
# global CSS: webfonts, typography, navigation, custom CSS
# =====================================================================

def used_fonts():
    """Font ids / family names referenced anywhere in content, typography, navigation or theme CSS."""
    text = json.dumps([PAGES, C['footers'], DESIGN['typography'], NAV], ensure_ascii=False)
    text += (SRC / 'theme' / 'legacy-theme.css').read_text(encoding='utf-8')
    ids = set(re.findall(r'font_[a-z0-9]{9}', text))
    fonts = DESIGN['webfonts'].get('fonts', {})
    families = {f['system-name'] for fid, f in fonts.items() if fid in ids or f['system-name'] in text}
    families |= {'EditorialNew-Regular', 'PPPangramSans-Bold', 'PPPangramSans-Semibold', 'Lexik-Regular-webfont'}  # aliases below
    return ids, families


def font_css():
    webfonts = DESIGN['webfonts']
    typo = DESIGN['typography']
    files = DESIGN['font_files']
    used_ids, used_families = used_fonts()
    out = ''
    for family, file in sorted(files.items()):
        if family in used_families:
            out += f"@font-face{{font-family:'{family}';src:url(../fonts/{file}) format('woff2');font-display:swap}}"
    # aliases used by the old theme stylesheet
    for alias, family in (('editorialR', 'EditorialNew-Regular'), ('panB', 'PPPangramSans-Bold'), ('panSB', 'PPPangramSans-Semibold'), ('Lexik', 'Lexik-Regular-webfont')):
        out += f"@font-face{{font-family:'{alias}';src:url(../fonts/{files[family]}) format('woff2');font-display:swap}}"
    for fid, font in webfonts.get('fonts', {}).items():
        if font['system-name'] not in used_families:
            continue
        sels = [f'.{fid}', f'[data-font="{fid}"]', f'[data-font="{fid}"] li a']
        for el in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p'):
            if typo.get(f'{el}_font_family') == fid:
                sels += ['#content-holder p', '#content-holder li'] if el == 'p' else [f'#content-holder {el}']
        name = font['system-name']
        out += f"{','.join(sels)}{{font-family:\"{name}\",{font.get('category', 'sans-serif')};font-weight:{font.get('font_weight', 400) or 400};font-style:normal}}"
    return out


def font_family_css(fid):
    font = DESIGN['webfonts'].get('fonts', {}).get(fid)
    if not font:
        return '"Open Sans",Arial,sans-serif;font-weight:400;font-style:normal'
    return f"\"{font['system-name']}\",{font.get('category', 'sans-serif')};font-weight:400;font-style:normal"


def typography_css():
    t = DESIGN['typography']
    out = ''
    for el in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p'):
        if t.get(f'{el}_customize') == 'on' or el == 'p':
            css = ''
            if f'{el}_font_size' in t:
                css += f"font-size:{t[el + '_font_size']};"
            if f'{el}_line_height' in t:
                css += f"line-height:{t[el + '_line_height']};"
            if f'{el}_letter_spacing' in t:
                css += f"letter-spacing:{t[el + '_letter_spacing']};"
            if css:
                sel = '#content-holder p,#content-holder li' if el == 'p' else f'#content-holder {el}'
                out += f'{sel}{{{css}}}'
    if 'p_line_height' in t:
        out += f"#content-holder .is-content p{{margin-bottom:{t['p_line_height']}em}}"
    for sid, style in (t.get('custom') or {}).items():
        css = ''
        for key, value in style.items():
            prop = key.replace('custom_style_', '').replace('_', '-')
            if prop == 'font-family':
                css += f'font-family:{font_family_css(value)};'
            elif prop == 'text-stroke':
                css += f"-webkit-text-stroke:{value} {style.get('custom_style_text_stroke_color', '#000')};"
            elif prop in ('color', 'text-transform', 'font-size', 'letter-spacing', 'text-decoration', 'text-decoration-color',
                          'background-color', 'padding', 'border-color', 'border-width', 'border-style') or (prop == 'line-height' and style.get('custom_style_element') == 'block'):
                css += f'{prop}:{value};'
        out += f'#content-holder .{sid}{{{css}}}'
    return out


def advanced_css():
    a = DESIGN['advanced']
    out = f".is-content{{color:{a.get('text_color', '#222')}}}a{{color:{a.get('link_color', '#222')}}}a:hover{{color:{a.get('mouseover_color', '#000')}}}"
    out += f".back-to-top svg{{fill:{a.get('top_arrow_color', '#222')};width:{a.get('top_arrow_width', '53px')}}}"
    out += a.get('custom_css_global', '')
    for bp, query in [('xl', ' and (min-width: 1170px)')] + list(BREAKPOINTS.items()):
        if a.get(f'custom_css_{bp}'):
            out += f"@media screen{query}{{{a['custom_css_' + bp]}}}"
    return out


def nav_css():
    n = NAV
    sel = f".{n['id']}"
    return (
        f"{sel}{{height:{n['navbar_height']};background-color:{n.get('navbar_bg_color', 'transparent')}}}"
        f"{sel} .navbar-inner .navbar-left{{left:{n['navbar_padding']}}}"
        f"{sel} .navbar-inner .navbar-right{{right:{n['navbar_padding']}}}"
        f"{sel} .navbar-inner .logo{{margin-top:{n['logo_margin']};align-items:{n['logo_alignment']}}}"
        f"{sel} .logo img{{width:{n['logo_img_width']}}}"
        f"{sel} .navbar-inner nav ul li a span{{font-size:{n['menu_fontsize']};color:{n['menu_color']};text-transform:{n['menu_text_transform']};"
        f"border-bottom:{n['menu_border']} solid {n['menu_border_color']};padding-bottom:{n['menu_border_padding']}}}"
        f"{sel} .navbar-inner nav ul li a{{padding:0 {float(n['menu_padding'].replace('rem', '')) / 2}rem}}"
        f"{sel} .navbar-inner nav ul li a:hover span{{color:{n['menu_mouseover_color']};border-bottom-color:{n['menu_border_mouseover_color']}}}"
        f"{sel} .hamburger a.menu-icon{{width:{n['hamburger_width']}}}"
        f"{sel} .hamburger a.menu-icon span{{height:{n['hamburger_thickness']}px}}"
    )


def legacy_theme_css():
    """The old theme stylesheet (style.css), with asset URLs pointing at the new site."""
    css = (SRC / 'theme' / 'legacy-theme.css').read_text(encoding='utf-8')
    css = re.sub(r'@font-face\s*\{[^}]*\}', '', css)
    page = Page(None, 'assets/css/')
    return page.rewrite(css)


def minify_css(css):
    css = re.sub(r'/\*.*?\*/', '', css, flags=re.S)
    css = re.sub(r'\s+', ' ', css)
    css = re.sub(r'\s*([{};:,>])\s*', r'\1', css)
    css = re.sub(r';}', '}', css)
    css = re.sub(r'[^{}]+\{\}', '', css)
    css = re.sub(r'@media[^{]+\{\}', '', css)
    return css.strip()


# =====================================================================
# page shell
# =====================================================================

ICON_UP = ('<svg width="53" height="20" viewBox="0 0 53 20" aria-hidden="true">'
           '<polygon points="43.886,16.221 42.697,17.687 26.5,4.731 10.303,17.688 9.114,16.221 26.5,2.312"/></svg>')


def menu_items(page):
    items = ''
    for item in C['menu']:
        url = page.rewrite(item['url']) if item['url'] else page.page_url(HOME_ID)
        items += f'<li><a href="{url}"><span>{esc(item["title"])}</span></a></li>'
    return items


def render_header(page, show_menu):
    menu = menu_items(page)
    logo = attachment_file(NAV.get('logo_img'))
    nav = f'<nav class="standard navbar-left" data-font="{NAV["menu_font_family"]}"><ul class="menu">{menu}</ul></nav>' if show_menu else ''
    return (
        f'<header class="{NAV["id"]} semplice-navbar sticky-nav" data-nav="logo-right-menu-left">'
        f'<div class="navbar-inner">{nav}'
        f'<div class="hamburger navbar-left"><button class="menu-icon" type="button" aria-label="Menü öffnen" aria-controls="overlay-menu" aria-expanded="false"><span></span></button></div>'
        f'<div class="logo navbar-right"><a href="{page.page_url(HOME_ID)}" title="{esc(SITE["tagline"])}">'
        f'<img src="{page.url(media(logo, 200))}" width="84" height="84" alt="Sigmund Freud Privatuniversität"></a></div>'
        f'</div></header>'
        f'<div id="overlay-menu" hidden><nav class="overlay-nav" data-font="{NAV["overlay_font_family"]}"><ul>{menu}</ul></nav></div>'
    )


def page_title(p):
    """Readable <title>: the first heading of the cover (the old site showed internal names like '01_artikel_buehler')."""
    if p['id'] == HOME_ID:
        return SITE['tagline']
    ram = p['content']
    order = ram['order']
    sections = (['cover'] if ram.get('cover_visibility') == 'visible' else []) + [s for s in order if s != 'cover']
    for sid in sections:
        rows = order.get(sid, {})
        rows = {'r': rows} if 'columns' in rows else rows
        for row in rows.values():
            for items in row['columns'].values():
                for cid in items:
                    m = ram.get(cid, {})
                    if m.get('module') == 'text':
                        heads = re.findall(r'<h1[^>]*>(.*?)</h1>', m['content']['xl'], re.S)
                        text = ' '.join(re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', h))).strip() for h in heads).strip()
                        if text:
                            return f"{text} – {SITE['tagline']}"
    return f"{p['title']} – {SITE['tagline']}"


def first_text(ram, limit=200):
    for key, m in ram.items():
        if isinstance(m, dict) and m.get('module') == 'text':
            for pm in re.finditer(r'<p[^>]*>(.*?)</p>', m['content']['xl'], re.S):
                text = re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', pm.group(1)))).strip()
                if len(text) > 80:
                    return text[:limit].rsplit(' ', 1)[0] + ' …'
    return SITE['tagline']


def darker(hex_color, amount=0.15, toward=(0x22, 0x22, 0x22)):
    """Mix a colour toward the site's dark grey (keeps the hue, lowers the lightness)."""
    rgb = [int(hex_color[i:i + 2], 16) for i in (1, 3, 5)]
    return '#' + ''.join(f'{round(c * (1 - amount) + t * amount):02x}' for c, t in zip(rgb, toward))


def tint_further_reading(ram, page_color):
    """The "Weiterlesen" block at the end of an article (the trailing run of #222222
    sections) used the same dark grey as the footer. Give it a darker shade of the
    article's own background instead, and make its heading dark to stay readable."""
    order = [s for s in ram['order'] if s != 'cover' and s in ram]
    tail = []
    for sid in reversed(order):
        if ram[sid].get('styles', {}).get('xl', {}).get('background-color', '').lower() != '#222222':
            break
        tail.append(sid)
    if not any('article-cards-overlay' in json.dumps(ram['order'][sid]) or any(
            'article-cards-overlay' in (ram.get(col, {}).get('classes') or '')
            for row in ({'r': ram['order'][sid]} if 'columns' in ram['order'][sid] else ram['order'][sid]).values()
            for col in row['columns']) for sid in tail):
        return
    shade = darker(page_color)
    for sid in tail:
        for st in ram[sid].get('styles', {}).values():
            if st.get('background-color', '').lower() == '#222222':
                st['background-color'] = shade
        section = ram['order'][sid]
        for row in ({'r': section} if 'columns' in section else section).values():
            for col, items in row['columns'].items():
                if 'article-cards-overlay' in (ram.get(col, {}).get('classes') or ''):
                    ram[col].setdefault('styles', {}).setdefault('xl', {})['opacity'] = '1'  # tint must not show through
                    continue
                for cid in items:
                    m = ram.get(cid, {})
                    if m.get('module') == 'spacer' and m.get('options', {}).get('background-color', '').lower() == '#222222':
                        m['options']['background-color'] = 'transparent'  # was invisible on the old dark grey
                    for st in m.get('styles', {}).values():  # dark divider strips, same reason
                        if (st.get('background-color') or '').lower() == '#222222':
                            st['background-color'] = 'transparent'
                    if m.get('module') == 'text':
                        m['content']['xl'] = re.sub(r'color: (rgb\(240, 232, 221\)|#f0e8dd)', 'color: #222222', m['content']['xl'])


def render_page(pid):
    p = PAGES[pid]
    path = page_path(pid)
    page = Page(pid, path)
    ram = p['content']
    is_home = pid == HOME_ID
    if is_home:
        prepare_home(ram)
        archive_data(page)
        update_counters(ram)
    page.motion_css_enabled = ram.get('branding', {}).get('scroll_reveal') == 'disabled'
    prepare_captions(ram)
    if p['type'] == 'project' and ram.get('branding', {}).get('background-color'):
        tint_further_reading(ram, ram['branding']['background-color'])

    body = render_sections(ram, page)
    footer_id = p['settings'].get('meta', {}).get('footer') or DESIGN['advanced'].get('global_footer')
    footer = ''
    if footer_id in C['footers']:
        footer = render_sections(C['footers'][footer_id]['content'], page, is_footer=True)

    archive_json = ''
    if is_home:
        body, data = render_archive(page, body)
        archive_json = json.dumps(data, ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/')

    branding = ram.get('branding', {})
    if branding.get('background-color'):
        page.css.append(f"body{{background-color:{branding['background-color']}}}")
    if branding.get('custom_post_css'):
        page.css.append(branding['custom_post_css'])
    has_cover = ram.get('cover_visibility') == 'visible'
    if not has_cover:
        page.css.append(f"#content-holder .sections{{margin-top:{NAV['navbar_height']}}}")

    css = minify_css(''.join(page.css + page.motion_css))
    title = page_title(p)
    head_extra = ''
    scripts = f'<script src="{page.url("assets/js/site.js")}" defer></script>'
    if is_home:
        scripts += (f'<script id="archiv-data" type="application/json">{archive_json}</script>'
                    f'<script src="{page.url("assets/js/archiv.js")}" data-leaflet="{page.url("assets/vendor/leaflet/")}" defer></script>')

    doc = f'''<!DOCTYPE html>
<html lang="de-AT">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{html.escape(first_text(ram))}">
<meta name="robots" content="noindex, nofollow">
<link rel="icon" href="{page.url(media(attachment_file(NAV.get('logo_img')), 64))}">
<link rel="stylesheet" href="{page.url('assets/css/site.css')}?v={ASSET_VERSION}">{head_extra}
<style>{css}</style>
</head>
<body class="{'is-home' if is_home else 'is-' + p['type']}" data-post-type="{p['type']}">
<a class="skip-link" href="#content-holder">Zum Inhalt springen</a>
{render_header(page, show_menu=not is_home)}
<main id="content-holder"><div class="sections">
{body}
</div>
<footer class="site-footer">{footer}</footer>
</main>
<div class="back-to-top"><a href="#" aria-label="Nach oben">{ICON_UP}</a></div>
{scripts}
</body>
</html>
'''
    dst = OUT / path / 'index.html'
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(doc, encoding='utf-8')
    return path, title


# =====================================================================
# main
# =====================================================================

ASSET_VERSION = 'dev'


def build_assets():
    global ASSET_VERSION
    css = '\n'.join([
        (SRC / 'theme' / 'base.css').read_text(encoding='utf-8'),
        legacy_theme_css(),
        font_css(),
        typography_css(),
        advanced_css(),
        nav_css(),
        (SRC / 'theme' / 'overrides.css').read_text(encoding='utf-8'),
    ])
    css = minify_css(css)
    ASSET_VERSION = hashlib.md5(css.encode()).hexdigest()[:8]
    (OUT / 'assets' / 'css').mkdir(parents=True, exist_ok=True)
    (OUT / 'assets' / 'css' / 'site.css').write_text(css, encoding='utf-8')
    for sub in ('js', 'vendor'):
        shutil.copytree(SRC / sub, OUT / 'assets' / sub, dirs_exist_ok=True, ignore=shutil.ignore_patterns('._*', '.DS_Store'))
    fonts = OUT / 'assets' / 'fonts'
    fonts.mkdir(parents=True, exist_ok=True)
    used = set(re.findall(r"url\(\.\./fonts/([^)]+)\)", css))
    for f in used:
        shutil.copy2(SRC / 'fonts' / f, fonts / f)


def main():
    for d in ('assets',):
        shutil.rmtree(OUT / d, ignore_errors=True)
    for html_file in OUT.glob('**/index.html'):
        html_file.unlink()
    OUT.mkdir(exist_ok=True)
    build_assets()
    built = []
    for pid in PAGES:
        built.append(render_page(pid))
    for path, title in sorted(built):
        print(f'  /{path:<55} {title}')
    # remove media variants that are no longer referenced
    referenced = set()
    for f in list(OUT.glob('**/*.html')) + [OUT / 'assets' / 'css' / 'site.css']:
        referenced |= set(re.findall(r'media/[^"\')\s,]+', f.read_text(encoding='utf-8')))
    removed = 0
    for f in (OUT / 'media').glob('**/*'):
        if f.is_file() and str(f.relative_to(OUT)) not in referenced:
            f.unlink()
            removed += 1
    # macOS writes AppleDouble "._" files on non-HFS drives; they don't belong on the server
    for f in OUT.glob('**/._*'):
        f.unlink()
    print(f'built {len(built)} pages, removed {removed} unused media files')


if __name__ == '__main__':
    main()
