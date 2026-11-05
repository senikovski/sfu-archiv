#!/usr/bin/env python3
"""
The webfonts are commercially licensed and must not be downloadable from the public
repository. They are committed only as source/fonts.enc (encrypted); the key lives in
the GitHub secret FONTS_KEY and in the local, untracked file .fonts-key.

  python3 tools/fonts.py encrypt   # after adding/replacing fonts in source/fonts/
  python3 tools/fonts.py decrypt   # used by the GitHub Action (FONTS_KEY env var)
"""
import io
import os
import sys
import tarfile
from pathlib import Path

from cryptography.fernet import Fernet

ROOT = Path(__file__).resolve().parent.parent
FONTS = ROOT / 'source' / 'fonts'
ENC = ROOT / 'source' / 'fonts.enc'
KEYFILE = ROOT / '.fonts-key'


def key():
    k = os.environ.get('FONTS_KEY') or (KEYFILE.read_text().strip() if KEYFILE.exists() else '')
    if not k:
        sys.exit('no key: set FONTS_KEY or create .fonts-key')
    return k.encode()


def encrypt():
    if not KEYFILE.exists() and not os.environ.get('FONTS_KEY'):
        KEYFILE.write_text(Fernet.generate_key().decode())
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode='w:gz') as tar:
        for f in sorted(FONTS.glob('*.woff2')):
            if not f.name.startswith('._'):
                tar.add(f, arcname=f.name)
    ENC.write_bytes(Fernet(key()).encrypt(buf.getvalue()))
    print(f'wrote {ENC.relative_to(ROOT)} ({ENC.stat().st_size // 1024} KB)')


def decrypt():
    data = Fernet(key()).decrypt(ENC.read_bytes())
    FONTS.mkdir(exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(data), mode='r:gz') as tar:
        tar.extractall(FONTS, filter='data')
    print(f'unpacked {len(list(FONTS.glob("*.woff2")))} fonts')


if __name__ == '__main__':
    {'encrypt': encrypt, 'decrypt': decrypt}[sys.argv[1]]()
