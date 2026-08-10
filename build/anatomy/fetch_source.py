#!/usr/bin/env python3
"""
fetch_source.py — download the BodyParts3D source archive into a local, gitignored cache.

The archive is 547 MB and is NEVER committed. Only the small derived GLBs under
docs/assets/anatomy/ are committed, and those carry the source's CC BY-SA 2.1 Japan licence
(see docs/assets/anatomy/LICENSE).

Run:
    python3 build/anatomy/fetch_source.py                 # download into build/anatomy/.cache/
    python3 build/anatomy/fetch_source.py --zip <path>    # register an already-downloaded copy
"""

import argparse
import os
import shutil
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, ".cache")
ZIP_NAME = "BodyParts3D_3.0_obj_95.zip"
URL = f"https://dbarchive.biosciencedbc.jp/data/bodyparts3d/20110915/{ZIP_NAME}"
EXPECTED_BYTES = 547270545


def cached_zip():
    return os.path.join(CACHE, ZIP_NAME)


def verify(path):
    """Return the archive path if it is present and the expected size, else raise."""
    if not os.path.exists(path):
        raise SystemExit(f"missing: {path}\nRun: python3 build/anatomy/fetch_source.py")
    size = os.path.getsize(path)
    if size != EXPECTED_BYTES:
        raise SystemExit(
            f"{path} is {size} bytes, expected {EXPECTED_BYTES}. "
            "The download is truncated or the upstream archive changed; delete it and refetch."
        )
    return path


def download(dest):
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    tmp = dest + ".part"
    print(f"downloading {URL}\n  -> {dest}  ({EXPECTED_BYTES/1e6:.0f} MB)")
    with urllib.request.urlopen(URL) as r, open(tmp, "wb") as f:
        done = 0
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
            done += len(chunk)
            pct = 100 * done / EXPECTED_BYTES
            print(f"\r  {done/1e6:7.0f} MB  {pct:5.1f}%", end="", file=sys.stderr)
    print(file=sys.stderr)
    os.replace(tmp, dest)
    return dest


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--zip", help="path to an already-downloaded BodyParts3D_3.0_obj_95.zip")
    args = ap.parse_args()

    dest = cached_zip()
    if args.zip:
        src = os.path.abspath(args.zip)
        verify(src)
        if src != dest:
            os.makedirs(CACHE, exist_ok=True)
            print(f"copying {src} -> {dest}")
            shutil.copy2(src, dest)
    elif os.path.exists(dest):
        print(f"already cached: {dest}")
    else:
        download(dest)

    verify(dest)
    print(f"ok: {dest}")


if __name__ == "__main__":
    main()
