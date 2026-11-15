"""Download the TED (Tenders Electronic Daily) data used in this case study.

Two official sources, because TED changed format in 2023 (legacy XML schema -> eForms):
  1. Legacy period (2016 - Oct 2023): the yearly "Contract award notices" CSV subsets published by the
     Publications Office on data.europa.eu (dataset "ted-csv"). One row per award (lot x winner).
  2. eForms period (Nov 2023 onwards): the TED Search API v3 (POST https://api.ted.europa.eu/v3/notices/search,
     no key needed for search) to find the notices, then the official notice XML (one GET per notice)
     to read which lot European Dynamics won and its value.

Polite collection: official endpoints only, one request at a time with a pause, files cached in data/raw/
(never re-downloaded if present). Reuse: TED data (c) European Union, reusable with attribution
(Commission Decision 2011/833/EU).

Usage:  python src/download_ted.py            (legacy CSV + API search + ED notice XML + market context)
"""
import io
import json
import time
import zipfile
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "ted"
CSV_URL = "https://data.europa.eu/api/hub/store/data/ted-contract-award-notices-{year}.zip"
API = "https://api.ted.europa.eu/v3/notices/search"
XML_URL = "https://ted.europa.eu/en/notice/{pub}/xml"
YEARS = range(2016, 2024)
PAUSE = 1.0
HEADERS = {"User-Agent": "open-data-case-study/1.0 (research; low frequency)"}

# Search fields kept for every eForms notice (notice-level, flat)
FIELDS = ["publication-number", "publication-date", "notice-type", "procedure-type", "buyer-name", "buyer-country",
          "buyer-legal-type", "main-classification-proc", "classification-cpv", "winner-name", "winner-country",
          "organisation-name-tenderer", "received-submissions-type-code", "received-submissions-type-val",
          "result-value-notice", "result-value-cur-notice", "total-value", "total-value-cur", "estimated-value-proc",
          "estimated-value-cur-proc", "identifier-lot", "result-lot-identifier", "contract-conclusion-date",
          "winner-decision-date", "procedure-accelerated", "contract-framework-agreement"]

ED_QUERY = ('notice-type IN (can-standard can-modif can-social can-desg can-tran) AND '
            '(winner-name ~ "European Dynamics" OR organisation-name-tenderer ~ "European Dynamics" '
            'OR tendering-party-name ~ "European Dynamics")')
EU_MARKET_QUERY = ('notice-type = can-standard AND main-classification-proc = 72* AND buyer-legal-type = eu-ins-bod-ag '
                   'AND publication-date >= 20231101')


def get(url, **kw):
    for attempt in range(4):
        try:
            r = requests.get(url, headers=HEADERS, timeout=300, **kw)
            if r.status_code == 200:
                return r
            print("  HTTP", r.status_code, url)
        except requests.RequestException as e:
            print("  retry", attempt, e)
        time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"failed: {url}")


def legacy_csv():
    out = RAW / "csv"
    out.mkdir(parents=True, exist_ok=True)
    for year in YEARS:
        target = out / f"can_{year}.csv"
        if target.exists():
            continue
        print("download CAN CSV", year)
        z = zipfile.ZipFile(io.BytesIO(get(CSV_URL.format(year=year)).content))
        name = max(z.namelist(), key=lambda n: z.getinfo(n).file_size)
        target.write_bytes(z.read(name))
        time.sleep(PAUSE)


def search(query, name):
    """Page through the search API (250 per page) and cache the raw JSON."""
    target = RAW / f"api_{name}.json"
    if target.exists():
        return json.loads(target.read_text(encoding="utf-8"))
    notices, page = [], 1
    while True:
        r = requests.post(API, json={"query": query, "fields": FIELDS, "limit": 250, "page": page,
                                     "scope": "ALL", "paginationMode": "PAGE_NUMBER"}, headers=HEADERS, timeout=120)
        r.raise_for_status()
        d = r.json()
        batch = d.get("notices", [])
        for n in batch:
            n.pop("links", None)
        notices += batch
        print(f"  {name}: page {page}, {len(notices)} / {d.get('totalNoticeCount')}")
        if not batch or len(notices) >= d.get("totalNoticeCount", 0):
            break
        page += 1
        time.sleep(PAUSE)
    target.write_text(json.dumps(notices, ensure_ascii=False), encoding="utf-8")
    return notices


def notice_xml(notices):
    out = RAW / "xml"
    out.mkdir(parents=True, exist_ok=True)
    for n in notices:
        pub = n["publication-number"]
        target = out / f"{pub}.xml"
        if target.exists():
            continue
        target.write_bytes(get(XML_URL.format(pub=pub)).content)
        time.sleep(PAUSE)
    print("  xml files:", len(list(out.glob("*.xml"))))


def market_by_buyer(ed_notices):
    """CPV 72 award notices (eForms period) of the national buyers that awarded at least one lot to ED."""
    names = set()
    for n in ed_notices:
        if "eu-ins-bod-ag" in (n.get("buyer-legal-type") or []):
            continue
        for lang_names in (n.get("buyer-name") or {}).values():
            names.update(x for x in lang_names[:1])
            break
    allrows = []
    for i, b in enumerate(sorted(names)):
        safe = b.replace('"', " ").replace("\\", " ")
        q = (f'notice-type = can-standard AND main-classification-proc = 72* AND publication-date >= 20231101 '
             f'AND buyer-name ~ "{safe}"')
        try:
            allrows += search(q, f"market_buyer_{i:03d}")
        except requests.HTTPError as e:
            print("  skip buyer", i, e)
        time.sleep(PAUSE)
    return allrows


def ecb_rates():
    """Official ECB euro reference rates, annual averages (used to convert non-EUR eForms values to EUR)."""
    target = RAW.parent / "ecb_exr_annual.csv"
    if target.exists():
        return
    url = ("https://data-api.ecb.europa.eu/service/data/EXR/A.DKK+SEK+PLN+GBP+CHF+CZK+HUF+RON+BGN+NOK+ISK+USD.EUR.SP00.A"
           "?format=csvdata&startPeriod=2016")
    target.write_bytes(get(url).content)


def cpv_list():
    """CPV 2008 code list (Common Procurement Vocabulary, official labels), published on TED."""
    target = RAW.parent / "ref" / "cpv_2008_xls.zip"
    if target.exists():
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(get("https://ted.europa.eu/documents/d/ted/cpv_2008_xls").content)


def main():
    RAW.mkdir(parents=True, exist_ok=True)
    cpv_list()
    ecb_rates()
    legacy_csv()
    ed = search(ED_QUERY, "ed_notices")
    notice_xml(ed)
    search(EU_MARKET_QUERY, "market_eu_institutions")
    market_by_buyer(ed)
    print("done")


if __name__ == "__main__":
    main()
