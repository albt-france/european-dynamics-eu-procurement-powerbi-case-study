"""Turn the raw TED / FTS downloads (data/raw/) into small staging extracts (data/processed/staging/).

What this script does (and does NOT do):
  * filters: award rows won (alone or in a group) by a European Dynamics entity, plus the CPV 72 (IT services)
    award rows of the same buyers and of all EU institutions (market context);
  * parses the eForms notice XML (2023+) to read, lot by lot, which tender won and who was in it;
  * drops every field that can hold a person's name (buyer / winner contact points, addresses, e-mails, phones);
  * keeps names raw: name resolution (variants, consortia), currency conversion, lot de-duplication and the star
    schema are done in T-SQL (sql/03_etl_dwh.sql), so the logic is visible and testable in the warehouse.

Usage:  python src/build_dataset.py
"""
import json
import re
import unicodedata
import xml.etree.ElementTree as ET
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "processed" / "staging"

ED_PATTERN = re.compile(r"europ\w*\s*dy\w{0,3}mics?|ευρωπαικη\s+δυναμικη|eurodyn", re.I)


def fold(s):
    """Upper-case, accent-free, single-spaced (used for matching only)."""
    s = unicodedata.normalize("NFD", str(s or ""))
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    return re.sub(r"\s+", " ", s).strip()


def is_ed(name):
    return bool(ED_PATTERN.search(fold(name).lower()))


# Company legal forms and organisation words (same list as ref.LegalFormToken in sql/02_reference_data.sql)
LEGAL_TOKENS = {"SA", "AG", "GMBH", "LTD", "LIMITED", "SARL", "SPA", "SRL", "NV", "BV", "AB", "OY", "OYJ", "AS", "SL",
                "SLU", "PLC", "INC", "LLP", "SE", "SAS", "KFT", "ZRT", "UAB", "AE", "IKE", "EPE", "CONSORTIUM", "GROUP",
                "SOLUTIONS", "SYSTEMS", "CONSULTING", "SERVICES", "TECHNOLOGIES", "BIETERGEMEINSCHAFT", "ARGE", "APS",
                "SPRL", "SRO", "DOO", "OU", "SIA", "LDA", "GIE", "CVBA", "BVBA", "KG", "CO", "CORPORATION", "SOFTWARE",
                "INFORMATIQUE", "OHG", "MBH", "SP", "ZOO", "GMBH&CO", "SCRL", "SC", "SNC", "SPRL", "ASA", "OYJ", "AD",
                "EOOD", "OOD", "DD", "SAU", "SCS", "LTDA", "PTY", "LLC", "CORP", "COMPANY", "INSTITUTE", "UNIVERSITY",
                "ASSOCIATION", "FOUNDATION", "STIFTUNG", "EV", "VZW", "ASBL", "UNIVERSITAT", "UNIVERSITE"}
HIDDEN = "Other supplier (name not kept)"


def is_organisation(name):
    """True when a supplier name contains a company legal form or an organisation word (not a person's name)."""
    tokens = set(re.sub(r"[^\w&]+", " ", fold(name).upper().replace(".", "")).split())
    spaced = " " + re.sub(r"[^\w]+", " ", fold(name).upper()) + " "
    return bool(tokens & LEGAL_TOKENS) or any(f" {t} " in spaced for t in ("S A", "S P A", "S R L", "SP Z O O", "S L"))


def protect(names, sep="---"):
    """Personal-data rule DQ-15, applied at ingestion: keep European Dynamics entities and organisations, replace any
    other winner name (possibly a sole trader, i.e. a person) by a neutral label."""
    if not isinstance(names, str) or not names.strip():
        return names
    return sep.join(n if (is_ed(n) or is_organisation(n)) else HIDDEN for n in names.split(sep))


def buyer_key(name):
    """Normalised buyer name: upper case, no accents / punctuation / legal noise. Used to link years and formats."""
    s = fold(name).upper()
    s = re.sub(r"\(.*?\)", " ", s)
    s = re.sub(r"[\W_]+", " ", s)          # keeps letters of every script (Greek, Cyrillic...)
    return re.sub(r"\s+", " ", s).strip()


# ---------------------------------------------------------------- 1. legacy CSV (2016 - 2023)
LEGACY_COLS = ["ID_NOTICE_CAN", "TED_NOTICE_URL", "YEAR", "ID_TYPE", "DT_DISPATCH", "CANCELLED", "CAE_NAME",
               "ISO_COUNTRY_CODE", "CAE_TYPE", "EU_INST_CODE", "TYPE_OF_CONTRACT", "B_FRA_AGREEMENT", "CPV", "ID_LOT",
               "LOTS_NUMBER", "VALUE_EURO", "TOP_TYPE", "B_ACCELERATED", "CRIT_CODE", "ID_AWARD", "ID_LOT_AWARDED",
               "INFO_ON_NON_AWARD", "B_AWARDED_TO_A_GROUP", "WIN_NAME", "WIN_COUNTRY_CODE", "B_CONTRACTOR_SME",
               "TITLE", "NUMBER_OFFERS", "AWARD_EST_VALUE_EURO", "AWARD_VALUE_EURO", "DT_AWARD", "B_EU_FUNDS"]


def legacy():
    frames = []
    for f in sorted((RAW / "ted" / "csv").glob("can_*.csv")):
        d = pd.read_csv(f, usecols=lambda c: c in LEGACY_COLS, dtype=str, low_memory=False)
        d = d[d.CANCELLED.fillna("0") == "0"]
        ed = d.WIN_NAME.fillna("").map(is_ed)
        keep = ed | d.CPV.fillna("").str.startswith("72")
        d = d[keep].copy()
        d["is_ed_raw"] = ed[keep]
        frames.append(d)
        print(f"  {f.name}: {int(ed.sum())} ED award rows, {int(keep.sum())} kept")
    d = pd.concat(frames, ignore_index=True)
    # TED publication number from the notice URL (e.g. ...TED:NOTICE:2-2019:TEXT... -> 2-2019)
    d["notice_id"] = d.TED_NOTICE_URL.str.extract(r"NOTICE:(\d+-\d{4})")[0]
    # joint procurement: "Buyer A---Buyer B---..." -> the first (lead) buyer, flag kept
    d["joint_procurement"] = d.CAE_NAME.fillna("").str.contains("---")
    d["CAE_NAME"] = d.CAE_NAME.fillna("").str.split("---").str[0].str.strip()
    d["buyer_key"] = d.CAE_NAME.map(buyer_key)
    d["WIN_NAME"] = d.WIN_NAME.map(protect)
    d.loc[~d.is_ed_raw, "TITLE"] = None      # titles kept for European Dynamics awards only (data minimisation)
    return d


# ---------------------------------------------------------------- 2. eForms XML (ED notices, 2023+)
def local(tag):
    return tag.rsplit("}", 1)[-1]


def kids(el, name):
    return [c for c in el if local(c.tag) == name]


def first(el, *path):
    """Follow a path of local names; return the first matching element (or None)."""
    cur = [el]
    for name in path:
        cur = [c for e in cur for c in e if local(c.tag) == name]
        if not cur:
            return None
    return cur[0]


def text(el, *path):
    e = first(el, *path) if path else el
    return e.text.strip() if e is not None and e.text else None


def parse_eforms(path):
    root = ET.parse(path).getroot()
    pub = path.stem
    notice_type = text(root, "NoticeTypeCode")
    procedure = text(root, "TenderingProcess", "ProcedureCode")
    # organisations (companies only; contact points are never read)
    orgs = {}
    for org in root.iter():
        if local(org.tag) != "Organization":
            continue
        comp = first(org, "Company")
        if comp is None:
            continue
        oid = text(comp, "PartyIdentification", "ID")
        natural = (text(org, "NaturalPersonIndicator") or "false") == "true"
        orgs[oid] = {"name": None if natural else text(comp, "PartyName", "Name"),
                     "country": text(comp, "PostalAddress", "Country", "IdentificationCode"),
                     "size": text(comp, "CompanySizeCode")}
    buyers = [p for p in kids(root, "ContractingParty")]
    # organisations acting as the buyer's procurement service provider (e.g. the e-procurement platform operator)
    service_providers = {text(sp, "Party", "PartyIdentification", "ID")
                         for b in buyers for sp in kids(first(b, "Party") if first(b, "Party") is not None else b,
                                                        "ServiceProviderParty")}
    b_ref = text(buyers[0], "Party", "PartyIdentification", "ID") if buyers else None
    b_type = text(buyers[0], "ContractingPartyType", "PartyTypeCode") if buyers else None
    buyer = orgs.get(b_ref, {})
    # lots
    lots = {}
    for lot in kids(root, "ProcurementProjectLot"):
        lid = text(lot, "ID")
        proj = first(lot, "ProcurementProject")
        est = first(proj, "RequestedTenderTotal", "EstimatedOverallContractAmount") if proj is not None else None
        lots[lid] = {"cpv": text(proj, "MainCommodityClassification", "ItemClassificationCode") if proj is not None else None,
                     "title": text(proj, "Name") if proj is not None else None,
                     "est": est.text if est is not None else None,
                     "est_cur": est.get("currencyID") if est is not None else None,
                     "framework": text(lot, "TenderingProcess", "ContractingSystem", "ContractingSystemTypeCode")}
    proc_proj = first(root, "ProcurementProject")
    proc_cpv = text(proc_proj, "MainCommodityClassification", "ItemClassificationCode") if proc_proj is not None else None
    # results (inside the eForms extension)
    res = next((e for e in root.iter() if local(e.tag) == "NoticeResult"), None)
    if res is None:
        return []
    tenders = {}
    for t in kids(res, "LotTender"):
        amt = first(t, "LegalMonetaryTotal", "PayableAmount")
        tenders[text(t, "ID")] = {"value": amt.text if amt is not None else None,
                                  "cur": amt.get("currencyID") if amt is not None else None,
                                  "party": text(t, "TenderingParty", "ID"), "lot": text(t, "TenderLot", "ID")}
    parties = {}
    for p in kids(res, "TenderingParty"):
        members = [text(m, "ID") for m in kids(p, "Tenderer")]
        parties[text(p, "ID")] = {"name": text(p, "Name"), "members": members}
    contracts = {}
    for c in kids(res, "SettledContract"):
        for tr in kids(c, "LotTender"):
            contracts[text(tr, "ID")] = text(c, "IssueDate")
    rows = []
    for lr in kids(res, "LotResult"):
        if (text(lr, "TenderResultCode") or "") != "selec-w":
            continue
        lid = text(lr, "TenderLot", "ID")
        n_tenders = None
        for st in kids(lr, "ReceivedSubmissionsStatistics"):
            if text(st, "StatisticsCode") == "tenders":
                n_tenders = text(st, "StatisticsNumeric")
        win_tenders = [text(t, "ID") for t in kids(lr, "LotTender")]
        for tid in win_tenders:
            t = tenders.get(tid, {})
            party = parties.get(t.get("party"), {"name": None, "members": []})
            names = [orgs.get(m, {}).get("name") for m in party["members"]]
            names = [n for n in names if n]
            if not any(is_ed(n) for n in names + [party["name"] or ""]):
                continue
            # Data-quality rule DQ-03: the tenderer reference points to the buyer's service provider (an ED entity
            # running the e-procurement platform) while the tendering party's own name is another company.
            ed_members = [m for m in party["members"] if is_ed(orgs.get(m, {}).get("name") or "")]
            # DQ-04: same pattern without a tendering-party name, on a non-IT CPV (works, supplies, other services).
            ed_sp = bool(ed_members) and all(m in service_providers for m in ed_members)
            lot = lots.get(lid, {})
            cpv = (lot.get("cpv") or proc_cpv or "")
            dq = ""
            if ed_sp and party["name"] and not is_ed(party["name"]):
                dq = "DQ-03 winner reference = buyer's service provider, tendering party is another company"
            elif ed_sp and not party["name"] and not cpv.startswith(("72", "48")):
                dq = "DQ-04 winner reference = buyer's service provider, non-IT contract"
            rows.append({
                "dq_excluded": dq, "ed_is_service_provider": ed_sp,
                "notice_id": pub, "notice_type": notice_type, "procedure_code": procedure,
                "buyer_name": buyer.get("name"), "buyer_country": buyer.get("country"), "buyer_legal_type": b_type,
                "lot_id": lid, "lots_number": len(lots), "cpv_main": lot.get("cpv") or proc_cpv,
                "title": lot.get("title"), "framework": lot.get("framework"),
                "est_value": lot.get("est"), "est_currency": lot.get("est_cur"),
                "award_value": t.get("value"), "award_currency": t.get("cur"),
                "n_tenders": n_tenders, "n_winning_tenders_in_lot": len(win_tenders),
                "tendering_party_name": protect(party["name"]), "winner_names": protect("---".join(names)),
                "winner_countries": "---".join(orgs.get(m, {}).get("country") or "" for m in party["members"]),
                "contract_date": contracts.get(tid),
            })
    return rows


def eforms_ed():
    meta = {n["publication-number"]: n for n in json.loads((RAW / "ted" / "api_ed_notices.json").read_text(encoding="utf-8"))}
    rows = []
    for f in sorted((RAW / "ted" / "xml").glob("*.xml")):
        try:
            r = parse_eforms(f)
        except ET.ParseError:
            print("  not eForms / unreadable:", f.name)
            continue
        for x in r:
            x["publication_date"] = (meta.get(f.stem, {}).get("publication-date") or "")[:10]
        rows += r
    d = pd.DataFrame(rows)
    d["buyer_key"] = d.buyer_name.map(buyer_key)
    return d


# ---------------------------------------------------------------- 3. eForms market context (API, notice level)
def first_name(v):
    if isinstance(v, dict):
        for lang in ("eng", "fra", "deu"):
            if v.get(lang):
                return v[lang][0]
        return next(iter(v.values()))[0] if v else None
    return v[0] if isinstance(v, list) and v else v


def eforms_market():
    rows = []
    for f in sorted((RAW / "ted").glob("api_market_*.json")):
        for n in json.loads(f.read_text(encoding="utf-8")):
            codes = n.get("received-submissions-type-code") or []
            vals = n.get("received-submissions-type-val") or []
            tenders = [int(v) for c, v in zip(codes, vals) if c == "tenders" and str(v).isdigit()]
            winners = (n.get("winner-name") or {})
            wl = first_name({k: v for k, v in winners.items()}) if winners else None
            all_w = next(iter(winners.values()), []) if winners else []
            rows.append({
                "notice_id": n["publication-number"], "publication_date": (n.get("publication-date") or "")[:10],
                "notice_type": n.get("notice-type"), "procedure_code": n.get("procedure-type"),
                "buyer_name": first_name(n.get("buyer-name")),
                "buyer_country": first_name(n.get("buyer-country")),
                "buyer_legal_type": first_name(n.get("buyer-legal-type")),
                "cpv_main": first_name(n.get("main-classification-proc")),
                "lots_with_result": len(n.get("result-lot-identifier") or []),
                "n_tenders_min": min(tenders) if tenders else None,
                "n_tenders_max": max(tenders) if tenders else None,
                "lots_single_tender": sum(1 for t in tenders if t == 1),
                "lots_with_stats": len(tenders),
                "total_value": n.get("total-value"), "total_currency": first_name(n.get("total-value-cur")),
                "first_winner": protect(wl),
                "has_ed": any(is_ed(w) for w in all_w),
            })
    d = pd.DataFrame(rows).drop_duplicates("notice_id")
    d["buyer_key"] = d.buyer_name.map(buyer_key)
    return d


# ---------------------------------------------------------------- 4. FTS (European Commission budget)
FTS_KEEP = {"Year": "year", "Name of beneficiary": "beneficiary_name", "Beneficiary country": "beneficiary_country",
            "Beneficiary’s contracted amount (EUR)": "contracted_eur",
            "Beneficiary’s estimated contracted amount (EUR)": "est_contracted_eur",
            "Beneficiary’s estimated consumed amount (EUR)": "est_consumed_eur",
            "Commitment  total amount (EUR) (A+B)": "commitment_total_eur",
            "Expense type": "expense_type", "Subject of grant or contract": "subject",
            "Responsible department": "department", "Budget line name": "budget_line_name",
            "Programme name": "programme_name", "Beneficiary type": "beneficiary_type",
            "Type of contract*": "contract_type", "Management type": "management_type",
            "Reference of the Legal Commitment (LC)": "legal_commitment_ref", "Reference (Budget)": "budget_ref"}


def fts():
    frames = []
    for f in sorted((RAW / "fts").glob("fts_*.xlsx")):
        d = pd.read_excel(f, dtype=str)
        d.columns = [c.strip() for c in d.columns]
        cols = {c: FTS_KEEP[k] for k in FTS_KEEP for c in d.columns if c.replace("  ", " ") == k.replace("  ", " ")}
        d = d[list(cols)].rename(columns=cols)
        d = d[d.beneficiary_name.fillna("").map(is_ed)]
        frames.append(d)
        print(f"  {f.name}: {len(d)} European Dynamics rows")
    return pd.concat(frames, ignore_index=True)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    print("legacy CSV")
    lg = legacy()
    print("eForms ED notices (XML)")
    ef = eforms_ed()
    print("eForms market (API)")
    mk = eforms_market()
    ed_buyers = set(lg.loc[lg.is_ed_raw, "buyer_key"]) | set(ef.loc[ef.dq_excluded == "", "buyer_key"])
    eu = lg.CAE_TYPE.fillna("").str.startswith("5")
    lg = lg[lg.is_ed_raw | (lg.CPV.fillna("").str.startswith("72") & (lg.buyer_key.isin(ed_buyers) | eu))]
    mk = mk[mk.cpv_main.fillna("").str.startswith("72")
            & (mk.buyer_key.isin(ed_buyers) | (mk.buyer_legal_type == "eu-ins-bod-ag"))]
    lg.drop(columns=["TED_NOTICE_URL"]).to_csv(OUT / "ted_legacy_awards.csv", index=False, encoding="utf-8")
    ef.to_csv(OUT / "ted_eforms_ed_awards.csv", index=False, encoding="utf-8")
    mk.to_csv(OUT / "ted_eforms_market_notices.csv", index=False, encoding="utf-8")
    fx = pd.read_csv(RAW / "ecb_exr_annual.csv", usecols=["CURRENCY", "TIME_PERIOD", "OBS_VALUE"])
    fx.columns = ["currency", "year", "units_per_eur"]
    fx.to_csv(OUT / "ecb_exr_annual.csv", index=False)
    print("FTS")
    fts().to_csv(OUT / "fts_ed.csv", index=False, encoding="utf-8")
    print(f"legacy rows {len(lg):,} (ED {int(lg.is_ed_raw.sum())}), eForms ED award rows {len(ef)}, "
          f"eForms market notices {len(mk):,}")
    import build_reference          # CPV labels and countries for the codes kept above
    build_reference.main()


if __name__ == "__main__":
    main()
