#!/usr/bin/env python3
"""Download the four official Meituan tables into Git-ignored directories."""

from __future__ import annotations

import argparse
import hashlib
import shutil
import ssl
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path

import certifi


REPO_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = REPO_ROOT / "data" / "raw"
DOWNLOAD_DIR = REPO_ROOT / "data" / "downloads"
MANIFEST_PATH = REPO_ROOT / "reports" / "DOWNLOAD_MANIFEST.md"
OFFICIAL_REPOSITORY = "https://github.com/meituan/Meituan-INFORMS-TSL-Research-Challenge"
SOURCE_COMMIT = "1f9b4288cee5a78d1e5da007fc306bbaa662fc6d"
RAW_BASE = (
    "https://raw.githubusercontent.com/meituan/"
    f"Meituan-INFORMS-TSL-Research-Challenge/{SOURCE_COMMIT}"
)


@dataclass(frozen=True)
class SourceFile:
    remote_name: str
    local_name: str
    zipped: bool = False

    @property
    def url(self) -> str:
        return f"{RAW_BASE}/{self.remote_name}"


SOURCES = (
    SourceFile(
        "all_waybill_info_meituan_0322.csv.zip",
        "all_waybill_info_meituan_0322.csv",
        zipped=True,
    ),
    SourceFile("courier_wave_info_meituan.csv", "courier_wave_info_meituan.csv"),
    SourceFile("dispatch_rider_meituan.csv", "dispatch_rider_meituan.csv"),
    SourceFile("dispatch_waybill_meituan.csv", "dispatch_waybill_meituan.csv"),
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def download(url: str, destination: Path, force: bool) -> None:
    if destination.exists() and destination.stat().st_size > 0 and not force:
        print(f"reuse {destination.relative_to(REPO_ROOT)}")
        return

    destination.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": "phase1-data-audit/1.0"})
    try:
        context = ssl.create_default_context(cafile=certifi.where())
        with urllib.request.urlopen(request, timeout=120, context=context) as response:
            if response.status != 200:
                raise RuntimeError(f"HTTP {response.status}: {url}")
            with tempfile.NamedTemporaryFile(
                dir=destination.parent, prefix=f".{destination.name}.", suffix=".part", delete=False
            ) as temporary:
                shutil.copyfileobj(response, temporary)
                temporary_path = Path(temporary.name)
    except (urllib.error.URLError, TimeoutError) as error:
        raise RuntimeError(f"download failed: {url}: {error}") from error

    if temporary_path.stat().st_size == 0:
        temporary_path.unlink(missing_ok=True)
        raise RuntimeError(f"empty download: {url}")
    temporary_path.replace(destination)
    print(f"downloaded {destination.relative_to(REPO_ROOT)}")


def extract_expected(archive: Path, expected_name: str, destination: Path, force: bool) -> None:
    if destination.exists() and destination.stat().st_size > 0 and not force:
        print(f"reuse {destination.relative_to(REPO_ROOT)}")
        return
    with zipfile.ZipFile(archive) as zipped:
        members = [name for name in zipped.namelist() if not name.endswith("/")]
        matching = [name for name in members if Path(name).name == expected_name]
        if len(matching) != 1:
            raise RuntimeError(
                f"expected exactly one {expected_name!r} in {archive.name}, found {matching}"
            )
        destination.parent.mkdir(parents=True, exist_ok=True)
        with zipped.open(matching[0]) as source, tempfile.NamedTemporaryFile(
            dir=destination.parent, prefix=f".{destination.name}.", suffix=".part", delete=False
        ) as temporary:
            shutil.copyfileobj(source, temporary)
            temporary_path = Path(temporary.name)
        if temporary_path.stat().st_size == 0:
            temporary_path.unlink(missing_ok=True)
            raise RuntimeError(f"empty extracted file: {expected_name}")
        temporary_path.replace(destination)
    print(f"extracted {destination.relative_to(REPO_ROOT)}")


def write_manifest(download_rows: list[tuple[str, str, int, str]], raw_rows: list[tuple[str, int, str]]) -> None:
    lines = [
        "# 官方数据下载校验清单",
        "",
        f"- 官方仓库：<{OFFICIAL_REPOSITORY}>",
        f"- 固定提交：`{SOURCE_COMMIT}`",
        "- 本清单只包含文件名、来源、字节数和 SHA-256，不包含数据内容。",
        "",
        "## 下载文件",
        "",
        "| 文件 | 官方固定版本 URL | 字节数 | SHA-256 |",
        "|---|---|---:|---|",
    ]
    for name, url, size, digest in download_rows:
        lines.append(f"| `{name}` | <{url}> | {size} | `{digest}` |")
    lines.extend(
        [
            "",
            "## 解压后验收文件",
            "",
            "| 文件 | 字节数 | SHA-256 |",
            "|---|---:|---|",
        ]
    )
    for name, size, digest in raw_rows:
        lines.append(f"| `{name}` | {size} | `{digest}` |")
    lines.extend(
        [
            "",
            "原始文件位于 `data/raw/`，下载附件位于 `data/downloads/`；两者均被 Git 忽略。",
            "",
        ]
    )
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="redownload all official files")
    args = parser.parse_args()

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    download_rows: list[tuple[str, str, int, str]] = []
    raw_rows: list[tuple[str, int, str]] = []

    for source in SOURCES:
        if source.zipped:
            downloaded = DOWNLOAD_DIR / source.remote_name
            download(source.url, downloaded, args.force)
            extract_expected(downloaded, source.local_name, RAW_DIR / source.local_name, args.force)
        else:
            downloaded = RAW_DIR / source.local_name
            download(source.url, downloaded, args.force)
        download_rows.append(
            (source.remote_name, source.url, downloaded.stat().st_size, sha256(downloaded))
        )

    for source in SOURCES:
        raw_path = RAW_DIR / source.local_name
        raw_rows.append((source.local_name, raw_path.stat().st_size, sha256(raw_path)))
    write_manifest(download_rows, raw_rows)
    print(f"wrote {MANIFEST_PATH.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
