"""Generate docs/MEASURES.md and docs/DATA_DICTIONARY.md from the model definition and the warehouse.
Usage:  python src/build_docs.py
"""
import sys
import warnings
from pathlib import Path

import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).parent))
from build_tmdl import CALC_ITEMS, MEASURES, RELATIONSHIPS, TABLES, AXIS  # noqa: E402
from load_sql import connect, DATABASE  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"

# worked examples (the value a reader sees in the report with no filter, computed in SQL for the doc)
EXAMPLES = {
    "ED Awards": "SELECT COUNT(*) FROM dwh.FactAward WHERE IsED = 1",
    "ED Buyers": "SELECT COUNT(DISTINCT BuyerKey) FROM dwh.FactAward WHERE IsED = 1",
    "ED Award Value": "SELECT FORMAT(SUM(ValueSplitEUR) / 1e6, 'N0') + ' M EUR' FROM dwh.FactAward WHERE IsED = 1",
    "ED Ceiling Value": "SELECT FORMAT(SUM(IIF(IsValueCounted = 1, ValueEUR, 0)) / 1e6, 'N0') + ' M EUR' FROM dwh.FactAward WHERE IsED = 1",
    "ED Median Award Value": "SELECT TOP 1 FORMAT(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY ValueSplitEUR) OVER (), 'N0') + ' EUR' "
                             "FROM dwh.FactAward WHERE IsED = 1 AND ValueSplitEUR IS NOT NULL",
    "ED Share from EU Institutions": "SELECT FORMAT(AVG(IIF(b.IsEU = 1, 1.0, 0.0)), 'P0') FROM dwh.FactAward f JOIN dwh.DimBuyer b ON b.BuyerKey = f.BuyerKey WHERE f.IsED = 1",
    "ED Single-Offer Share": "SELECT FORMAT(AVG(IIF(NumberOfOffers = 1, 1.0, 0.0)), 'P0') FROM dwh.FactAward WHERE IsED = 1 AND NumberOfOffers IS NOT NULL",
    "Market Single-Offer Share": "SELECT FORMAT(AVG(IIF(NumberOfOffers = 1, 1.0, 0.0)), 'P0') FROM dwh.FactAward WHERE IsED = 0 AND NumberOfOffers IS NOT NULL",
    "FTS Contracted": "SELECT FORMAT(SUM(ContractedEUR) / 1e6, 'N0') + ' M EUR' FROM dwh.FactFts",
    "SLA Met %": "SELECT FORMAT(AVG(IIF(IsSlaMet = 1, 1.0, 0.0)), 'P1') FROM sim.FactServiceRequest WHERE IsClosed = 1",
}


def measures_md(cn):
    out = ["# DAX measures", "",
           "All measures live in the hidden-column table `_Measures`, grouped in display folders. Source of truth: "
           "`src/build_tmdl.py` (this file is generated from it). *Example* = value with no filter, checked in SQL.", "",
           "Conventions: `CALCULATE` adds or replaces filters on top of the current filter context (a slicer, a visual's "
           "axis); `DIVIDE` returns BLANK instead of an error on a zero denominator; boolean filters such as "
           "`FactAward[IsED] = TRUE ()` are rewritten by DAX as `FILTER ( ALL ( FactAward[IsED] ), ... )`, so they "
           "replace any existing filter on that column only.", ""]
    folder = None
    for name, dax, fmt, f, desc in MEASURES:
        if f != folder:
            out += [f"## {f}", ""]
            folder = f
        ex = ""
        if name in EXAMPLES:
            ex = f"  \n*Example:* {pd.read_sql(EXAMPLES[name], cn).iloc[0, 0]}"
        out += [f"### {name}", "", "```dax", f"{name} = {dax}", "```", f"{desc}{ex}  \nFormat: `{fmt or 'text'}`", ""]
    out += ["## Calculation group `Time Calc`", "",
            "One definition of each time variant, applied to whatever measure is in the visual (`SELECTEDMEASURE ()`). "
            "Put `Time Calc[Period]` on columns of a matrix and any measure in values.", ""]
    for name, dax, fmt in CALC_ITEMS:
        out += [f"* **{name}**: `{dax}`" + (f" (format {fmt})" if fmt else "")]
    out += ["", "## Field parameter `Axis`", "",
            "A calculated table built with `NAMEOF`; a slicer on `Axis[Axis]` swaps the column used by the visuals that "
            "reference it: " + ", ".join(f"{a} (`{t}[{c}]`)" for a, t, c in AXIS) + ".", ""]
    return "\n".join(out)


def dictionary_md(cn):
    cols = pd.read_sql("SELECT TABLE_SCHEMA s, TABLE_NAME t, COLUMN_NAME c, DATA_TYPE d FROM INFORMATION_SCHEMA.COLUMNS "
                       "WHERE TABLE_SCHEMA IN ('dwh','sim') ORDER BY TABLE_SCHEMA, TABLE_NAME, ORDINAL_POSITION", cn)
    counts = pd.read_sql("SELECT s.name + '.' + t.name AS tbl, SUM(p.rows) AS n FROM sys.tables t JOIN sys.schemas s "
                         "ON s.schema_id = t.schema_id JOIN sys.partitions p ON p.object_id = t.object_id AND p.index_id IN (0,1) "
                         "WHERE s.name IN ('dwh','sim') GROUP BY s.name, t.name", cn).set_index("tbl").n.to_dict()
    out = ["# Data dictionary", "",
           "## Sources", "",
           "| Source | What | Period | Access | Licence |", "|---|---|---|---|---|",
           "| TED - Contract award notices (CSV subset), Publications Office, data.europa.eu dataset `ted-csv` | one row per award | 2016 - Oct 2023 | yearly zip, `src/download_ted.py` | (c) EU, reuse with attribution (Decision 2011/833/EU) |",
           "| TED Search API v3 (`api.ted.europa.eu/v3/notices/search`) + notice XML (`ted.europa.eu/en/notice/{id}/xml`) | eForms notices: ED lots (XML) and CPV 72 market context (search fields) | Nov 2023 - 13 Nov 2026 | anonymous, paged, 1 request/s | same |",
           "| Financial Transparency System (FTS), European Commission | legal commitments by beneficiary, department, programme | 2016 - 2025 | yearly XLSX, `src/download_fts.py` | same |",
           "| ECB euro reference rates (data-api.ecb.europa.eu, EXR annual averages) | currency conversion of non-EUR eForms values | 2016 - 2026 | CSV API | ECB, reuse with source |",
           "| CPV 2008 code list (TED) | CPV labels and hierarchy | - | XLSX | (c) EU |",
           "| European Dynamics website (eurodyn.com) | company facts quoted in the report, *as stated by European Dynamics* | read 15 Nov 2026 | public pages | quoted, not redistributed |",
           "", "Retrieved on 15 November 2026. Personal data: contact points, addresses, e-mails and phone numbers of buyers "
           "and winners are never read; supplier names that do not look like an organisation are replaced by "
           "*Other supplier (name not kept)*.", "",
           "## Star schema (SQL Server `EuroDynDW`, Power BI model)", "",
           "Relationships (one-to-many, single direction): " + "; ".join(f"`{a}[{b}]` -> `{c}[{d}]`" for a, b, c, d in RELATIONSHIPS) + ".", ""]
    model_desc = {t[0]: t[1] for t in TABLES}
    for (s, t), g in cols.groupby(["s", "t"], sort=False):
        name = t
        out += [f"### `{s}.{t}` ({counts.get(f'{s}.{t}', 0):,} rows)", ""]
        if name in model_desc:
            out += [model_desc[name], ""]
        out += ["| Column | SQL type |", "|---|---|"] + [f"| {r.c} | {r.d} |" for r in g.itertuples()] + [""]
    out += ["## Power BI-only tables", "",
            "* `FactFts`, `DimDepartment`, `DimProgramme`: built in Power Query from the FTS extract (second source; "
            "PostgreSQL design, CSV fallback) - see `powerquery/FtsStaging.pq`. `FactFts` relates to `DimEntity` on "
            "`EntityCode` and to the two FTS dimensions on their text keys.",
            "* `Time Calc` (calculation group), `Axis` (field parameter), `ML Feature Importance`, `ML Metrics`, "
            "`QualityChecks`, `_Measures`.", ""]
    return "\n".join(out)


def main():
    cn = connect(DATABASE)
    DOCS.mkdir(exist_ok=True)
    (DOCS / "MEASURES.md").write_text(measures_md(cn), encoding="utf-8")
    (DOCS / "DATA_DICTIONARY.md").write_text(dictionary_md(cn), encoding="utf-8")
    print("docs: MEASURES.md, DATA_DICTIONARY.md")


if __name__ == "__main__":
    main()
