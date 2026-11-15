"""Build and execute notebooks/analysis.ipynb (collection summary, data checks, SQL answers, ML model).
Usage:  python src/build_notebook.py
"""
from pathlib import Path

import nbformat as nbf
from nbconvert.preprocessors import ExecutePreprocessor

ROOT = Path(__file__).resolve().parents[1]
NB = ROOT / "notebooks" / "analysis.ipynb"

cells = [
    ("md", "# European Dynamics in EU public procurement - collection, checks and model\n"
           "One notebook for the parts that are not in SQL or Power BI: what was collected, the data checks, a few "
           "answers straight from the warehouse, and the single-offer model. Run the pipeline first (README, *How to rerun*)."),
    ("code", "import sys, json, warnings\nfrom pathlib import Path\nimport pandas as pd\nwarnings.filterwarnings('ignore')\n"
             "ROOT = Path.cwd().parent if Path.cwd().name == 'notebooks' else Path.cwd()\nsys.path.insert(0, str(ROOT / 'src'))\n"
             "from load_sql import connect, DATABASE\ncn = connect(DATABASE)\nST = ROOT / 'data' / 'processed' / 'staging'\n"
             "pd.set_option('display.max_colwidth', 80)"),
    ("md", "## 1. Collection (official sources only, low frequency)\n"
           "* **TED legacy CSV** (data.europa.eu, *Contract award notices* 2016-2023): one row per award.\n"
           "* **TED Search API v3** + notice **XML** (eForms, Nov 2023 - Nov 2026): lot-level results of the notices naming "
           "European Dynamics; notice-level CPV 72 context of the same buyers and of EU institutions.\n"
           "* **FTS** yearly datasets 2016-2025 (European Commission).\n* **ECB** annual euro reference rates; **CPV 2008** labels.\n"
           "Scripts: `src/download_ted.py`, `src/download_fts.py`, filtering in `src/build_dataset.py`."),
    ("code", "sizes = {f.name: len(pd.read_csv(f, dtype=str)) for f in sorted(ST.glob('*.csv'))}\npd.Series(sizes, name='rows').to_frame()"),
    ("md", "## 2. Data checks\nThe warehouse runs 16 checks (`sql/06_quality_checks.sql`). PASS / WARN / FAIL:"),
    ("code", "pd.read_sql('SELECT CheckId, CheckName, Actual, Status FROM qa.CheckResult ORDER BY CheckId', cn)"),
    ("md", "### Name resolution\nRaw spellings of European Dynamics entities and the entity they resolve to (alias table "
           "`ref.EntityAlias`, LIKE patterns on a normalised name)."),
    ("code", "pd.read_sql('''SELECT TOP 12 RawName, EntityName, SourceSystem, Occurrences FROM pbi.vEntityNameMap\n"
             "                ORDER BY Occurrences DESC''', cn)"),
    ("md", "### eForms rows excluded (DQ-03 / DQ-04)\nIn some eForms notices the winner reference points to the organisation "
           "that the same notice lists as the buyer's **service provider** (a European Dynamics entity), while the "
           "tendering party is another company or the contract is not IT. These rows are excluded, not counted as awards."),
    ("code", "x = pd.read_csv(ST / 'ted_eforms_ed_awards.csv', dtype=str)\n"
             "x['rule'] = x.dq_excluded.fillna('kept').str[:5]\nx.groupby(['rule', 'buyer_country']).size().unstack(fill_value=0)"),
    ("md", "## 3. Answers from the warehouse (SQL, window functions)"),
    ("code", "pd.read_sql('''WITH y AS (SELECT d.[Year], COUNT(*) AS Awards FROM dwh.FactAward f JOIN dwh.DimDate d ON d.DateKey = f.DateKey\n"
             "                         WHERE f.IsED = 1 GROUP BY d.[Year])\n"
             "SELECT [Year], Awards, AVG(1.0 * Awards) OVER (ORDER BY [Year] ROWS BETWEEN 2 PRECEDING AND CURRENT ROW) AS MovingAvg3Y\n"
             "FROM y ORDER BY [Year]''', cn).round(1)"),
    ("code", "pd.read_sql('''SELECT p.ProcedureFamily, SUM(IIF(f.IsED = 1, 1, 0)) AS EdLots,\n"
             "  AVG(IIF(f.IsED = 1, IIF(f.NumberOfOffers = 1, 1.0, 0.0), NULL)) AS EdSingleOffer,\n"
             "  AVG(IIF(f.IsED = 0, IIF(f.NumberOfOffers = 1, 1.0, 0.0), NULL)) AS OtherSingleOffer\n"
             "FROM dwh.FactAward f JOIN dwh.DimProcedure p ON p.ProcedureKey = f.ProcedureKey\n"
             "WHERE f.NumberOfOffers IS NOT NULL GROUP BY p.ProcedureFamily ORDER BY EdLots DESC''', cn).round(3)"),
    ("md", "## 4. Model: will an IT-services lot receive a single offer?\n"
           "Target: `NumberOfOffers = 1` on CPV 72 lots (all suppliers). Features known at publication: procedure, framework, "
           "buyer type and country, CPV group, log value, year, TED format. Missing values imputed, categories one-hot encoded "
           "(rare levels grouped), 5-fold stratified cross-validation, permutation importance on a held-out 25%."),
    ("code", "import ml_single_offer\nml_single_offer.main()"),
    ("md", "**Reading.** The procedure type carries most of the signal: negotiated procedures without a prior call are, by "
           "design, often single-offer. Buyer country comes next (national market structure), then value. **Limits:** "
           "notices are not independent (same buyers, same frameworks), the number of offers is missing for part of the "
           "notices, eForms market data are at notice level, and the model describes patterns - it does not judge any "
           "procurement or supplier. A single offer is not an anomaly in itself."),
]


def main():
    nb = nbf.v4.new_notebook()
    nb.cells = [nbf.v4.new_markdown_cell(t) if k == "md" else nbf.v4.new_code_cell(t) for k, t in cells]
    nb.metadata["kernelspec"] = {"name": "python3", "display_name": "Python 3", "language": "python"}
    ExecutePreprocessor(timeout=600, kernel_name="python3").preprocess(nb, {"metadata": {"path": str(NB.parent)}})
    NB.write_text(nbf.writes(nb), encoding="utf-8")
    print("notebook executed:", NB.relative_to(ROOT))


if __name__ == "__main__":
    main()
