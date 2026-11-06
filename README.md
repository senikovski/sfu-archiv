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
  sanity.json       which Sanity project holds the Personen/Orte database
  data/*.csv        the original Personen / Orte tables (now only a fallback, see below)
  media/            original images & video (only the ones the site uses)
  fonts/            webfonts as WOFF2 (not in Git – licensed; see "Fonts")
  fonts.enc         the same fonts, encrypted, for the GitHub build
  theme/            CSS: base.css (layout grid), legacy-theme.css (the original
                    custom CSS by ostblok), overrides.css (additions)
  js/               site.js (menu, back-to-top), archiv.js (Personen/Orte)
  vendor/leaflet/   Leaflet 1.9.4 (map library, self-hosted)
studio/    ← Sanity Studio (the editing interface), deployed to sfu-archiv.sanity.studio
tools/
  build.py                   source/ (+ Sanity) → site/
  sanity_state.py            fingerprint of the Sanity content (used to skip unneeded builds)
  fonts.py                   encrypt/decrypt the font files
  import_to_sanity.py        one-time import of the CSV tables into Sanity
  import_cards_to_sanity.py  one-time import of the original homepage cards into Sanity
  export_from_wordpress.py   one-time export from the old WordPress backup
.github/workflows/build.yml  builds + publishes the site automatically
```

## Editing the archive (Personen, Orte)

People and places are edited in **Sanity Studio: https://sfu-archiv.sanity.studio**
(log in with the Google account that owns the Sanity project; more editors can be
invited under sanity.io/manage → project "SFU" → Members).

- **Personen**: name, Lebensdaten, Kurztext, Porträt (optional thumbnail), linked
  Artikel / Personen / Orte, and places without a map entry ("Weitere Orte").
- **Orte**: name, address, text, image, coordinates (decimal degrees, e.g. from
  Google Maps → right-click a place), linked Artikel / Personen.
- **Artikel**: title + author, and which article page of the website it links to.
  The article *pages* themselves are not in Sanity (they're in `content.json`).
- "Reihenfolge" sets the position in the name list / the number on the map.

### Artikel: homepage cards and new articles

Every article is an **Artikel** entry in Sanity with three tabs:

- **Kachel auf der Startseite** – *Darstellung* (normal card / highlighted full-width
  card / not on the homepage), *Reihenfolge* (the existing articles are numbered
  10, 20, 30 …; use e.g. 25 to place a new one in between), card title, teaser and image.
  Normal cards are laid out in rows of three, highlighted ones get their own row.
- **Artikelseite** – for the 15 original articles only *Bestehende Seite* is set
  (their pages stay exactly as designed). For a **new article** leave that empty and
  fill in: Web-Adresse (click "Generate"), colour, Titelbild, introduction, author
  box, the text (paragraphs, sub-headings, lists, quotes, images with caption and
  source), Bibliographie and optionally the three "Weiterlesen" articles (default:
  the next ones in homepage order).
- **Personen & Orte** – the article appears on these people's/places' cards on the
  homepage, and as tags on the article page that jump to them.

New cards and pages are generated from copies of the original parts (the
"Psychotechnik" card, the Caruso highlight, the Bühler article), so they look like
the rest of the site. If you edit the card text or image of one of the original
articles, its card is regenerated the same way.

After you click **Publish**, the website updates by itself: GitHub checks Sanity every
10 minutes and rebuilds when something changed (a build takes ~1–2 minutes). To
publish immediately: GitHub → repository → Actions → "Build & deploy" → Run workflow.

The homepage counters "32 Personen" / "12 Orte" follow the number of entries.

Test version: **https://senikovski.github.io/sfu-archiv/** (GitHub Pages).
Repository: https://github.com/senikovski/sfu-archiv

### Changing the Studio (fields, labels)

The schema is in `studio/schemaTypes/`. To try changes locally and publish them:

```sh
cd studio && npm install && npm run dev     # http://localhost:3333
npx sanity deploy                           # updates sfu-archiv.sanity.studio
```

(npm doesn't work on exFAT drives like the "Flightcase" disk – copy `studio/` to the
internal disk first.)

### Moving to the SFU server later

Only the last step of `.github/workflows/build.yml` changes: instead of deploying to
GitHub Pages, upload `site/` to the SFU web folder via SFTP (e.g. with an rsync/SFTP
action and the server credentials stored as GitHub secrets). Nothing else changes.

### Fonts

The webfonts (Editorial New, PP Pangram Sans, Lexik) are commercially licensed, so the
public repository only contains them encrypted (`source/fonts.enc`). The key is the
GitHub secret `FONTS_KEY` and the local file `.fonts-key` (keep a copy somewhere safe).
After changing fonts: `python3 tools/fonts.py encrypt`.

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
pip install pillow certifi  # once
python3 tools/build.py          # reads Personen/Orte from Sanity
python3 tools/build.py --csv    # …or from source/data/*.csv (offline)
```

The build renders every page from `source/content.json`, converts images to
WebP (cached, so rebuilds take a few seconds), and writes `site/`.

Typical edits:

- **Personen / Orte**: in Sanity Studio (see above). The CSV files are kept only as
  an offline fallback and are no longer updated.
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
