# Psychologie im Nationalsozialismus — static rebuild

A lightweight rebuild of the SFU archive site
(psychologie-im-nationalsozialismus.sfu.ac.at). The old site was WordPress + the
Semplice 5 theme; this version is plain HTML/CSS with a little vanilla JavaScript.
It needs no database, PHP or CMS and runs on any static web host.

Homepage, measured (images and fonts not included):

| | old (WordPress/Semplice) | new |
|---|---|---|
| HTML | 325 KB (35 KB gzip) | 140 KB (20 KB gzip) |
| CSS + JS | 1.85 MB in 20 files (460 KB gzip), jQuery, GSAP, Leaflet twice | 55 KB in 3 files (12 KB gzip) + Leaflet 160 KB, loaded only when the map scrolls into view |
| server | PHP + MySQL | any static host |
| whole site incl. images | WordPress install + backups, several GB | about 13 MB |

## Folder layout

```
site/      ← the finished website. Upload the contents of this folder.
source/    ← everything the site is built from
  content.json      pages, articles, footer, media index, design settings
                    (exported from the WordPress database)
  data/*.csv        Personen / Orte databases (homepage archive + map)
  media/            original images & video (only the ones the site uses)
  fonts/            webfonts as WOFF2
  theme/            CSS: base.css (layout grid), legacy-theme.css (the original
                    custom CSS by ostblok), overrides.css (additions)
  js/               site.js (menu, back-to-top), archiv.js (Personen/Orte)
  vendor/leaflet/   Leaflet 1.9.4 (map library, self-hosted)
tools/
  build.py                   source/ → site/
  export_from_wordpress.py   one-time export from the old WordPress backup
```

## Preview locally

```sh
cd site
python3 -m http.server 8000
# open http://localhost:8000
```

(Opening the HTML files directly with `file://` mostly works, but links to folders
like `artikel/…/` need a web server.)

## Rebuild after changing something

```sh
pip install pillow          # once
python3 tools/build.py
```

The build renders every page from `source/content.json`, converts images to
WebP (cached, so rebuilds take a few seconds), and writes `site/`.

Typical edits:

- **Personen / Orte**: edit `source/data/personen.csv` / `orte.csv`
  (semicolon-separated, same columns as before). Portraits are matched by
  file name like before: `source/media/2021/11/NN_Vorname_Nachname.png` and
  `Thumbnail_NN_Vorname_Nachname.png`. NN is the row number starting at 00.
  Note that the "Long" column holds the latitude and "Lat" the longitude, as in
  the original file.
- **Texts of articles/pages**: they're in `source/content.json` as HTML inside
  each module (`"module": "text"` → `content.xl`). For small fixes you can also
  edit `site/…/index.html` directly, but a rebuild will overwrite that.
- **Styles**: `source/theme/*.css`.

## How it works

`tools/build.py` is a small port of the Semplice renderer. Each page is
sections → rows → columns → modules (text, image, button, spacer, code,
gallery), and the per-breakpoint styles stored by Semplice become a small inline
`<style>` per page. Element ids and classes are the same as before, so the
original custom CSS still applies unchanged. Things the old theme did in the
browser (responsive font sizes, moving the "Die Autoren" box, the Rohracher
three-image card) are now done at build time. The Personen list and Orte list
are generated as HTML, and `archiv.js` adds the interactive card and the map.

## Notes

- `robots: noindex, nofollow` is kept from the old site (WordPress had "discourage
  search engines" turned on). Remove the line in `render_page()` in
  `tools/build.py` if the archive should appear in search engines.
- The map tiles still come from the Mapbox style of the original designers
  (ostblok), using their public access token in `source/js/archiv.js`. If that
  account is ever closed, swap `TILES` for another tile provider.
- URLs are unchanged (`/`, `/about/`, `/artikel/<slug>/`), so existing links keep
  working.
- `2022/04/Hofstätter.jpg` (Charakterologie article) wasn't in the local WordPress
  backup, so it was downloaded from the live site into `source/media/`.
- Two article references in `orte.csv` have no published target: "Smoking Gun – Ein
  Kommentar" (never published) and "Entnazifizierung als Zumutung" (no link). They
  show as plain text instead of dead links.
- Output file names are ASCII-only (`Hofstätter.jpg` → `Hofstatter-960.webp`), so
  any web server can serve them.
