#!/usr/bin/env python3
"""Print a short fingerprint of the published Sanity content (number of entries +
latest change). The scheduled GitHub Action compares it with the live site's
build-info.txt and only rebuilds when something changed."""
import json
import ssl
import urllib.parse
import urllib.request
from pathlib import Path

cfg = json.loads((Path(__file__).resolve().parent.parent / 'source' / 'sanity.json').read_text())
q = ('{"n": count(*[_type in ["person","ort","artikel"] && !(_id in path("drafts.**"))]),'
     ' "t": *[_type in ["person","ort","artikel"] && !(_id in path("drafts.**"))] | order(_updatedAt desc)[0]._updatedAt}')
url = (f"https://{cfg['projectId']}.api.sanity.io/v{cfg.get('apiVersion', '2024-01-01')}/data/query/"
       f"{cfg['dataset']}?query={urllib.parse.quote(q)}")
try:
    import certifi  # python.org builds on macOS ship without root certificates
    ctx = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    ctx = ssl.create_default_context()
r = json.load(urllib.request.urlopen(url, timeout=30, context=ctx))['result']
print(f"{r['n']}@{r['t']}")
