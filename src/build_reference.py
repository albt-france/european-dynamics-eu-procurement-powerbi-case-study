"""Reference extracts for the warehouse: CPV labels (official CPV 2008 list) and countries.

Writes data/processed/staging/ref_cpv.csv (every CPV code used in the staging extracts, plus its parent levels)
and ref_country.csv (ISO 2 / ISO 3 / name / EU membership). Usage:  python src/build_reference.py
"""
import io
import zipfile
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
ST = ROOT / "data" / "processed" / "staging"

# ISO2 (TED legacy uses UK and GR), ISO3 (eForms), name, EU member in 2026
COUNTRIES = """AT,AUT,Austria,1;BE,BEL,Belgium,1;BG,BGR,Bulgaria,1;HR,HRV,Croatia,1;CY,CYP,Cyprus,1;CZ,CZE,Czechia,1;
DK,DNK,Denmark,1;EE,EST,Estonia,1;FI,FIN,Finland,1;FR,FRA,France,1;DE,DEU,Germany,1;GR,GRC,Greece,1;HU,HUN,Hungary,1;
IE,IRL,Ireland,1;IT,ITA,Italy,1;LV,LVA,Latvia,1;LT,LTU,Lithuania,1;LU,LUX,Luxembourg,1;MT,MLT,Malta,1;
NL,NLD,Netherlands,1;PL,POL,Poland,1;PT,PRT,Portugal,1;RO,ROU,Romania,1;SK,SVK,Slovakia,1;SI,SVN,Slovenia,1;
ES,ESP,Spain,1;SE,SWE,Sweden,1;UK,GBR,United Kingdom,0;CH,CHE,Switzerland,0;NO,NOR,Norway,0;IS,ISL,Iceland,0;
MK,MKD,North Macedonia,0;RS,SRB,Serbia,0;BA,BIH,Bosnia and Herzegovina,0;UA,UKR,Ukraine,0;KH,KHM,Cambodia,0;
PS,PSE,Palestine,0;ME,MNE,Montenegro,0;AL,ALB,Albania,0;GE,GEO,Georgia,0;MD,MDA,Moldova,0;TR,TUR,Turkey,0"""


def main():
    rows = [r.strip().split(",") for r in COUNTRIES.replace("\n", "").split(";")]
    pd.DataFrame(rows, columns=["iso2", "iso3", "country_name", "is_eu_member"]).to_csv(ST / "ref_country.csv", index=False)

    z = zipfile.ZipFile(ROOT / "data" / "raw" / "ref" / "cpv_2008_xls.zip")
    name = [n for n in z.namelist() if n.lower().endswith((".xls", ".xlsx"))][0]
    cpv = pd.read_excel(io.BytesIO(z.read(name)), usecols=["CODE", "EN"], dtype=str)
    cpv["code"] = cpv.CODE.str[:8]
    labels = dict(zip(cpv.code, cpv.EN.str.strip()))

    used = set()
    lg = pd.read_csv(ST / "ted_legacy_awards.csv", usecols=["CPV"], dtype=str).CPV
    ef = pd.read_csv(ST / "ted_eforms_ed_awards.csv", usecols=["cpv_main"], dtype=str).cpv_main
    mk = pd.read_csv(ST / "ted_eforms_market_notices.csv", usecols=["cpv_main"], dtype=str).cpv_main
    for s in (lg, ef, mk):
        used |= set(s.dropna().str[:8])

    def parent(code, n):
        """CPV level code: first n significant digits padded with zeros (division = 2, group = 3, class = 4, category = 5)."""
        return code[:n].ljust(8, "0")

    out = []
    for c in sorted(used):
        row = {"cpv_code": c, "cpv_label": labels.get(c, "(code not in CPV 2008 list)")}
        for lvl, n in (("division", 2), ("group", 3), ("class", 4), ("category", 5)):
            p = parent(c, n)
            row[f"{lvl}_code"] = p
            row[f"{lvl}_label"] = labels.get(p, labels.get(parent(c, n - 1), ""))
        out.append(row)
    pd.DataFrame(out).to_csv(ST / "ref_cpv.csv", index=False, encoding="utf-8")
    print(f"countries {len(rows)}, CPV codes {len(out)}")


if __name__ == "__main__":
    main()
