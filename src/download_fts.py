"""Download the yearly Financial Transparency System (FTS) datasets of the European Commission.

FTS lists the recipients of funds managed directly by the Commission (grants, procurement contracts, prizes...)
by year of commitment, with the Directorate-General / service, budget line, programme and amount.
Source: https://ec.europa.eu/budget/financial-transparency-system/ (yearly XLSX, English version).
Reuse: (c) European Union, reusable with attribution (Commission Decision 2011/833/EU).

Usage:  python src/download_fts.py
"""
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "fts"
URL = "https://ec.europa.eu/budget/financial-transparency-system/download/{year}_FTS_dataset_en.xlsx"
YEARS = range(2016, 2026)
HEADERS = {"User-Agent": "open-data-case-study/1.0 (research; low frequency)"}


def main():
    RAW.mkdir(parents=True, exist_ok=True)
    for year in YEARS:
        target = RAW / f"fts_{year}.xlsx"
        if target.exists():
            continue
        r = requests.get(URL.format(year=year), headers=HEADERS, timeout=600)
        if r.status_code != 200:
            print("not available:", year, r.status_code)
            continue
        target.write_bytes(r.content)
        print("downloaded", year, f"{len(r.content) / 1e6:.1f} MB")
        time.sleep(2)


if __name__ == "__main__":
    main()
