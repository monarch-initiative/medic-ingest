#!/usr/bin/env python3
"""Download source data files specified in download.yaml."""

import tarfile
import urllib.request
from pathlib import Path

import yaml


def download_files():
    """Download all files specified in download.yaml."""
    with open("download.yaml") as f:
        config = yaml.safe_load(f)

    downloads = config.get("downloads", [])
    if not downloads:
        print("No downloads configured in download.yaml")
        return

    for item in downloads:
        url = item["url"]
        local_name = item["local_name"]
        local_path = Path(local_name)
        tar_extract = item.get("tar_extract")

        # For tarball downloads, check if extracted files already exist
        if tar_extract:
            all_exist = all(Path(e["dest"]).exists() for e in tar_extract)
            if all_exist:
                print(f"Skipping {local_name} (extracted files already exist)")
                continue

        local_path.parent.mkdir(parents=True, exist_ok=True)

        if not local_path.exists():
            print(f"Downloading {url} -> {local_name}")
            urllib.request.urlretrieve(url, local_path)
            print(f"  Downloaded {local_path.stat().st_size:,} bytes")
        else:
            print(f"Skipping download of {local_name} (already exists)")

        if tar_extract:
            print(f"Extracting from {local_name}...")
            with tarfile.open(local_path) as tf:
                for entry in tar_extract:
                    src = entry["src"]
                    dest = Path(entry["dest"])
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    member = tf.getmember(src)
                    with tf.extractfile(member) as src_f, open(dest, "wb") as dst_f:
                        dst_f.write(src_f.read())
                    print(f"  Extracted {src} -> {dest}")


if __name__ == "__main__":
    download_files()
