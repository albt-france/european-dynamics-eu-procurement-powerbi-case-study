"""8-page PDF report (landscape 16:9): HTML + inline SVG charts, printed to PDF by headless Edge.
Every number comes from the warehouse or the pipeline outputs; none is typed in the text.
Power BI captures are used where they exist (docs/img/powerbi_p{n}.png, taken in Power BI Desktop).

Usage: python src/build_report.py   -> docs/EuropeanDynamics_PowerBI_CaseStudy.pdf, docs/img/*.png
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
import warnings
from pathlib import Path

import pandas as pd
from jinja2 import Template

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).parent))
import charts as C  # noqa: E402
from build_tmdl import MEASURES  # noqa: E402
from load_sql import connect, DATABASE  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DOCS, TMP = ROOT / "docs", ROOT / ".tmp"
PDF = DOCS / "EuropeanDynamics_PowerBI_CaseStudy.pdf"
FOOTER = "Independent case study based on public data · not affiliated with or endorsed by European Dynamics"
AI_NOTE = ("AI-assisted workflow: I used Claude, mainly to write scripts faster. I drove the project: I defined the "
           "questions, chose and validated the data sources, made the analytical decisions and checked every result.")

CSS = """
@page { size: 16in 9in; margin: 0 }
* { box-sizing: border-box; margin: 0; padding: 0 }
body { font-family: 'Segoe UI', system-ui, sans-serif; color: #0B0B0B; background: #F4F4F2; }
.page { width: 1536px; height: 864px; padding: 30px 40px 16px; display: flex; flex-direction: column;
        background: #F4F4F2; page-break-after: always; overflow: hidden; position: relative }
header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 12px; min-height: 58px }
h1 { font-size: 24px; font-weight: 700; line-height: 1.2; max-width: 1250px; letter-spacing: -0.2px }
.sub { color: #52514E; font-size: 13.5px; margin-top: 6px; max-width: 1270px; line-height: 1.4 }
.tag { font-size: 11.5px; font-weight: 700; letter-spacing: .8px; color: #52514E; border: 1px solid #C9C7BF;
       border-radius: 4px; padding: 4px 9px; white-space: nowrap; margin-top: 6px; background: #FCFCFB }
.tag.sim { color: #1C5CAB; border-color: #86B6EF } .tag.real { color: #0E7A55; border-color: #8FD3B8 }
.kpis { display: grid; gap: 14px; margin-bottom: 12px }
.card { background: #FCFCFB; border: 1px solid #E1E0D9; border-radius: 8px; padding: 12px 16px; display: flex;
        flex-direction: column; min-height: 0; overflow: hidden }
.kpi { padding: 11px 17px }
.klabel { font-size: 11px; font-weight: 700; color: #52514E; letter-spacing: .5px; text-transform: uppercase }
.kval { font-size: 29px; font-weight: 700; margin-top: 2px; line-height: 1.15 } .kval.blue { color: #1C5CAB }
.knote { font-size: 12.5px; color: #52514E; margin-top: 3px; line-height: 1.35 }
.grid { display: grid; gap: 14px; flex: 1; min-height: 0 }
.card h3 { font-size: 13.5px; font-weight: 600; margin-bottom: 6px }
.body { flex: 1; min-height: 0; display: flex; align-items: center; justify-content: center; font-size: 13px; line-height: 1.45 }
.body svg { width: 100%; height: 100% } .body img { max-width: 100%; max-height: 100%; border: 1px solid #E1E0D9; border-radius: 4px }
.body.text { display: block; overflow: hidden; color: #2B2A28 }
.body.text p { margin-bottom: 7px } .body.text ul, .body.text ol { margin: 0 0 6px 18px } .body.text li { margin-bottom: 4px }
table { border-collapse: collapse; width: 100%; font-size: 12px }
th { text-align: left; color: #52514E; font-weight: 600; border-bottom: 1px solid #C9C7BF; padding: 3px 5px }
td { padding: 3px 5px; border-bottom: 1px solid #EEEDE8; vertical-align: top } td.n, th.n { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap }
footer { font-size: 10.5px; color: #898781; margin-top: 8px }
.lab { font-weight: 700; color: #52514E; font-size: 12px; letter-spacing: .4px }
.flow { display: flex; gap: 8px; align-items: stretch; width: 100% }
.flow div.s { flex: 1; border: 1px solid #86B6EF; background: #EEF5FD; border-radius: 6px; padding: 8px; font-size: 12.5px; text-align: center }
.flow div.s b { display: block; color: #1C5CAB; margin-bottom: 3px } .flow div.a { color: #898781; font-size: 18px; align-self: center }
.mono { font-family: Consolas, monospace; font-size: 11.5px; background: #F1F0EB; padding: 1px 4px; border-radius: 3px }
pre.dax { font-family: Consolas, monospace; font-size: 11.2px; background: #F1F0EB; border-radius: 5px; padding: 7px 9px;
          white-space: pre-wrap; margin-bottom: 7px; line-height: 1.35 }
.ai { border-left: 3px solid #2A78D6; padding: 6px 10px; background: #EEF5FD; font-size: 13px; margin-top: 4px }
a { color: #1C5CAB; text-decoration: none }
"""

PAGE = Template("""
<section class="page">
  <header><div><h1>{{ p.title }}</h1>{% if p.subtitle %}<p class="sub">{{ p.subtitle }}</p>{% endif %}</div>
  {% if p.tag %}<div class="tag {{ p.tag_class }}">{{ p.tag }}</div>{% endif %}</header>
  {% if p.kpis %}<div class="kpis" style="grid-template-columns: repeat({{ p.kpis|length }}, 1fr)">
    {% for k in p.kpis %}<div class="card kpi"><div class="klabel">{{ k[0] }}</div><div class="kval blue">{{ k[1] }}</div><div class="knote">{{ k[2] }}</div></div>{% endfor %}
  </div>{% endif %}
  <div class="grid" style="grid-template-columns: {{ p.cols }}; grid-template-rows: {{ p.rows }}">
    {% for c in p.cards %}<div class="card" style="grid-column: {{ c.col }}; grid-row: {{ c.row }}">
      {% if c.title %}<h3>{{ c.title }}</h3>{% endif %}<div class="body {{ 'text' if c.text else '' }}">{{ c.body }}</div></div>{% endfor %}
  </div>
  <footer>{{ p.footer }} · {{ foot }}</footer>
</section>""")


def card(title, body, col="auto", row="auto", text=False):
    return dict(title=title, body=body, col=col, row=row, text=text)


def pct(x, d=0):
    return f"{100 * x:.{d}f}%"


def pbi(n: int, fallback: str) -> str:
    """Power BI capture of report page n if it was exported to docs/img, else the chart given."""
    f = DOCS / "img" / f"powerbi_p{n}.png"
    return f'<img src="{f.as_uri()}">' if f.exists() else fallback


def table(df, num=()):
    head = "".join(f"<th class='{'n' if c in num else ''}'>{c}</th>" for c in df.columns)
    rows = "".join("<tr>" + "".join(f"<td class='{'n' if c in num else ''}'>{v}</td>" for c, v in r.items()) + "</tr>"
                   for r in df.to_dict("records"))
    return f"<table><tr>{head}</tr>{rows}</table>"


# ======================================================================================
def build_pages():
    cn = connect(DATABASE)
    q = lambda s: pd.read_sql(s, cn)  # noqa: E731
    one = lambda s: q(s).iloc[0].to_dict()  # noqa: E731
    k = one("""SELECT COUNT(*) awards, COUNT(DISTINCT BuyerKey) buyers, COUNT(DISTINCT CountryKey) countries,
                      SUM(IIF(EdRole = 'Consortium with partners', 1.0, 0)) / COUNT(*) consortium,
                      SUM(IIF(IsFramework = 1, 1.0, 0)) / COUNT(*) framework,
                      SUM(ValueSplitEUR) split_value,
                      SUM(IIF(IsValueCounted = 1, ValueEUR, 0)) ceiling
               FROM dwh.FactAward WHERE IsED = 1""")
    k.update(one("SELECT AVG(IIF(b.IsEU = 1, 1.0, 0.0)) eu FROM dwh.FactAward f JOIN dwh.DimBuyer b ON b.BuyerKey = f.BuyerKey WHERE f.IsED = 1"))
    k.update(one("WITH b AS (SELECT BuyerKey, COUNT(*) n FROM dwh.FactAward WHERE IsED = 1 GROUP BY BuyerKey) "
                 "SELECT AVG(IIF(n >= 2, 1.0, 0.0)) repeat_rate FROM b"))
    k.update(one("SELECT SUM(ContractedEUR) fts, SUM(EstConsumedEUR) fts_cons FROM dwh.FactFts"))
    k.update(one("""SELECT SUM(IIF(f.IsED = 1, 1.0, 0)) / COUNT(*) share_n, SUM(IIF(f.IsED = 1, f.ValueSplitEUR, 0)) / SUM(f.ValueSplitEUR) share_v,
                           SUM(IIF(f.IsED = 1, 1, 0)) ed_it FROM dwh.FactAward f JOIN dwh.DimCPV c ON c.CpvKey = f.CpvKey WHERE c.IsITServices = 1"""))
    k.update(one("""SELECT AVG(IIF(IsED = 1, IIF(NumberOfOffers = 1, 1.0, 0.0), NULL)) so_ed, AVG(IIF(IsED = 0, IIF(NumberOfOffers = 1, 1.0, 0.0), NULL)) so_mkt,
                           AVG(IIF(IsED = 1, 1.0 * NumberOfOffers, NULL)) of_ed, AVG(IIF(IsED = 0, 1.0 * NumberOfOffers, NULL)) of_mkt
                    FROM dwh.FactAward WHERE NumberOfOffers IS NOT NULL"""))
    k.update(one("SELECT COUNT(*) rows_all FROM dwh.FactAward"))
    k.update(one("SELECT AVG(IIF(IsSlaMet = 1, 1.0, 0.0)) sla FROM sim.FactServiceRequest WHERE IsClosed = 1"))
    qa = q("SELECT CheckId, CheckName, Status FROM qa.CheckResult ORDER BY CheckId")
    ml = json.loads((ROOT / "data" / "processed" / "ml_metrics.json").read_text())
    fi = pd.read_csv(ROOT / "data" / "processed" / "ml_feature_importance.csv")
    for key in ("awards", "buyers", "countries", "rows_all", "ed_it"):
        k[key] = int(k[key])
    names = int(q("SELECT COUNT(DISTINCT RawName) n FROM dwh.EntityNameMap").iloc[0, 0])
    k["entities"] = q("SELECT COUNT(DISTINCT EntityCode) n FROM dwh.EntityNameMap WHERE EntityCode <> 'NONE'").iloc[0, 0]

    yr = q("""SELECT d.[Year], SUM(IIF(b.IsEU = 1, 1, 0)) EU, SUM(IIF(b.IsEU = 0, 1, 0)) [National]
              FROM dwh.FactAward f JOIN dwh.DimDate d ON d.DateKey = f.DateKey JOIN dwh.DimBuyer b ON b.BuyerKey = f.BuyerKey
              WHERE f.IsED = 1 GROUP BY d.[Year] ORDER BY 1""")
    yr["MovingAvg"] = (yr.EU + yr.National).rolling(3, min_periods=1).mean()
    peak = yr.assign(t=yr.EU + yr.National)
    first3, last3 = peak.t.iloc[:3].mean(), peak.t.iloc[-4:-1].mean()
    grp = q("""SELECT TOP 8 REPLACE(REPLACE(REPLACE(b.BuyerGroup, 'National or federal authority', 'National authority'),
                      'Body governed by public law', 'Public-law body'), 'EU agency or other EU body', 'EU agencies and bodies')
                      + IIF(b.IsEU = 1, '', ' (' + ISNULL(c.CountryName, '?') + ')') g, COUNT(*) n
               FROM dwh.FactAward f JOIN dwh.DimBuyer b ON b.BuyerKey = f.BuyerKey LEFT JOIN dwh.DimCountry c ON c.CountryKey = f.CountryKey
               WHERE f.IsED = 1 GROUP BY b.BuyerGroup, b.IsEU, c.CountryName ORDER BY 2 DESC""")
    ctry = q("""SELECT TOP 9 c.CountryName, COUNT(*) n FROM dwh.FactAward f JOIN dwh.DimCountry c ON c.CountryKey = f.CountryKey
                WHERE f.IsED = 1 GROUP BY c.CountryName ORDER BY 2 DESC""")
    cpv = q("""SELECT TOP 6 c.DivisionCode + ' ' + LEFT(c.DivisionLabel, 38) d, COUNT(*) n FROM dwh.FactAward f JOIN dwh.DimCPV c ON c.CpvKey = f.CpvKey
               WHERE f.IsED = 1 GROUP BY c.DivisionCode + ' ' + LEFT(c.DivisionLabel, 38) ORDER BY 2 DESC""")
    cls = q("""SELECT TOP 7 c.ClassLabel d, COUNT(*) n FROM dwh.FactAward f JOIN dwh.DimCPV c ON c.CpvKey = f.CpvKey
               WHERE f.IsED = 1 GROUP BY c.ClassLabel ORDER BY 2 DESC""")
    short = {"IT services: consulting, software development, Internet and support": "IT services (consulting, software, support)",
             "Software programming and consultancy services": "Software programming and consultancy",
             "Computer support and consultancy services": "Computer support and consultancy",
             "Programming services of packaged software products": "Programming of packaged software",
             "Software package and information systems": "Software packages and IS"}
    cls["d"] = cls.d.map(lambda x: short.get(x, x[:34]))
    prog = q("""SELECT p.ProgrammeFamily f, SUM(x.ContractedEUR) v FROM dwh.FactFts x JOIN dwh.DimProgramme p
                ON p.ProgrammeKey = x.ProgrammeKey GROUP BY p.ProgrammeFamily ORDER BY 2 DESC""")
    proc = q("""SELECT p.ProcedureFamily f, SUM(IIF(x.IsED = 1, 1, 0)) n,
                       AVG(IIF(x.IsED = 1, IIF(x.NumberOfOffers = 1, 1.0, 0.0), NULL)) ed,
                       AVG(IIF(x.IsED = 0, IIF(x.NumberOfOffers = 1, 1.0, 0.0), NULL)) mk
                FROM dwh.FactAward x JOIN dwh.DimProcedure p ON p.ProcedureKey = x.ProcedureKey
                WHERE x.NumberOfOffers IS NOT NULL GROUP BY p.ProcedureFamily HAVING SUM(IIF(x.IsED = 1, 1, 0)) >= 5 ORDER BY 2 DESC""")
    share = q("""SELECT d.[Year], SUM(IIF(f.IsED = 1, 1.0, 0)) / COUNT(*) s FROM dwh.FactAward f JOIN dwh.DimDate d ON d.DateKey = f.DateKey
                 JOIN dwh.DimCPV c ON c.CpvKey = f.CpvKey WHERE c.IsITServices = 1 GROUP BY d.[Year] ORDER BY 1""")
    fts = q("SELECT [Year], SUM(ContractedEUR) Contracted, SUM(EstConsumedEUR) Consumed FROM dwh.FactFts GROUP BY [Year] ORDER BY 1")
    dg = q("""SELECT TOP 8 d.DepartmentCode c, SUM(f.ContractedEUR) v FROM dwh.FactFts f JOIN dwh.DimDepartment d
              ON d.DepartmentKey = f.DepartmentKey GROUP BY d.DepartmentCode ORDER BY 2 DESC""")
    top3 = dg.v.iloc[:3].sum() / fts.Contracted.sum()
    ftype = q("SELECT TOP 1 ContractType t, SUM(ContractedEUR) / (SELECT SUM(ContractedEUR) FROM dwh.FactFts) s FROM dwh.FactFts GROUP BY ContractType ORDER BY 2 DESC").iloc[0]
    slag = q("""SELECT a.AgencyName n, AVG(IIF(r.IsSlaMet = 1, 1.0, 0.0)) s FROM sim.FactServiceRequest r JOIN sim.DimAgency a ON a.AgencyKey = r.AgencyKey
                WHERE r.IsClosed = 1 GROUP BY a.AgencyName ORDER BY 2""")
    perf_v1 = pd.read_csv(ROOT / "data" / "processed" / "perf_sql_v1.csv")
    perf_v2 = pd.read_csv(ROOT / "data" / "processed" / "perf_sql.csv")
    pf = perf_v2[perf_v2.state.str.startswith("before")][["query", "logical_reads"]].rename(columns={"logical_reads": "before"})
    pf["first"] = perf_v1[perf_v1.state.str.startswith("after")].logical_reads.values
    pf["tuned"] = perf_v2[perf_v2.state.str.startswith("after")].logical_reads.values
    pf["query"] = pf["query"].str.replace(r" \(.*\)", "", regex=True)
    names_tbl = q("""WITH x AS (
                        SELECT LEFT(RawName, 62) [Raw spelling], EntityName [Resolved entity], SourceSystem [Source], Occurrences [Rows],
                               CASE WHEN RawName LIKE N'%Dyamics%' THEN 1 WHEN RawName LIKE N'%Deutschlang%' THEN 2
                                    WHEN RawName LIKE N'%ΔΥΝΑΜ%' OR RawName LIKE N'%Δυναμ%' THEN 3
                                    WHEN RawName LIKE N'%ED LUXEMBOURG%' THEN 4 WHEN RawName LIKE N'%Advance Systems%' THEN 5
                                    WHEN RawName LIKE N'%group leader for lot%' THEN 6 WHEN RawName LIKE N'%SYSTEMSOF%' THEN 7
                                    WHEN RawName LIKE N'Bietergemeinschaft%' THEN 8 END AS grp
                        FROM pbi.vEntityNameMap),
                     r AS (SELECT *, ROW_NUMBER() OVER (PARTITION BY grp ORDER BY [Rows] DESC) rn FROM x WHERE grp IS NOT NULL)
                     SELECT TOP 6 [Raw spelling], [Resolved entity], [Source], [Rows] FROM r WHERE rn = 1 ORDER BY grp""")
    competitors = q("""WITH e AS (SELECT DISTINCT BuyerKey FROM dwh.FactAward WHERE IsED = 1)
                       SELECT TOP 6 f.WinnerLabel w, COUNT(DISTINCT f.BuyerKey) b FROM dwh.FactAward f JOIN e ON e.BuyerKey = f.BuyerKey
                       JOIN dwh.DimCPV c ON c.CpvKey = f.CpvKey WHERE f.IsED = 0 AND c.IsITServices = 1
                       AND f.WinnerLabel NOT IN ('Other supplier (name not kept)', 'Supplier not stated')
                       GROUP BY f.WinnerLabel ORDER BY 2 DESC""")
    y0, y1 = int(yr.Year.min()), int(yr.Year.max())
    pages = []

    # 0 Overview --------------------------------------------------------------------
    qs = ("<ol><li><b>Where and for whom does European Dynamics win EU public contracts?</b><br>"
          f"{pct(k['eu'])} of awards from EU institutions and agencies, the rest from national administrations in "
          f"{k['countries']} buyer countries; {pct(k['repeat_rate'])} of {k['buyers']} buyers came back at least once.</li>"
          "<li><b>How has this evolved since 2016, across the 2023 change of TED format?</b><br>"
          f"Between {int(peak.t.min())} and {int(peak.t.max())} awards a year (median {peak.t.median():.0f}), with a dip in "
          "2024, the first full eForms year, then back to the usual level (p.1).</li>"
          "<li><b>In which domains, with how much competition?</b><br>"
          f"IT services (CPV 72) almost only; {k['of_ed']:.1f} offers on average on its lots ({k['of_mkt']:.1f} on the others), "
          f"single-offer lots {pct(k['so_ed'])} vs {pct(k['so_mkt'])} (p.2).</li>"
          "<li><b>What is its place among the IT contracts of the same buyers?</b><br>"
          f"{pct(k['share_n'], 1)} of CPV 72 lots, {pct(k['share_v'], 1)} of their equal-split value (p.2).</li>"
          "<li><b>What does the EU budget commit to it?</b><br>"
          f"€{k['fts'] / 1e6:,.0f}M of Commission legal commitments 2016-2025 - commitments, not payments, and only the "
          "Commission's own budget (p.3).</li></ol>"
          "<p><span class='lab'>AND THE JOB ITSELF</span> &nbsp;every step a Power BI specialist owns: SQL Server warehouse and "
          "T-SQL ETL, PostgreSQL design for a second source, Power Query (folding, fuzzy merge, dataflow-ready), star schema, "
          f"{len(MEASURES)} DAX measures, calculation group, field parameter, RLS, performance, accessibility, workspace governance.</p>")
    flow = ('<div class="flow">' + '<div class="a">→</div>'.join(
        f'<div class="s"><b>{a}</b>{b}</div>' for a, b in [
            ("1. Collect", "TED CSV + API v3 + XML<br>FTS, ECB, CPV"),
            ("2. SQL Server", "stg → dwh star<br>T-SQL ETL, 16 checks"),
            ("3. Power Query", "folding views<br>FTS fuzzy merge"),
            ("4. Model + DAX", f"star schema<br>{len(MEASURES)} measures, RLS"),
            ("5. Report", "5 pages, alt text<br>governed in Service")]) + "</div>")
    recs = ("<ol><li><b>Count before you sum.</b> Framework values are ceilings shared by several winners: the report leads with "
            "awards and buyers, shows an equal-split value, and keeps the full ceiling only as an upper bound.</li>"
            f"<li><b>Repeat buyers are the core.</b> {pct(k['repeat_rate'])} of buyers awarded more than once: a buyer-level view "
            "(renewal dates, framework end dates) is the natural next dashboard for a bid team.</li>"
            "<li><b>Read FTS next to TED.</b> TED says what was awarded (ceilings), FTS what the Commission committed per year: "
            "together they bound the real volume of EU-level business.</li>"
            "<li><b>Feed data quality back.</b> The eForms service-provider referencing issue (DQ-03) is worth reporting to the "
            "Publications Office: it makes the TED index list a platform operator as winner of unrelated contracts.</li></ol>")
    pages.append(dict(
        title="European Dynamics in EU public procurement: a Power BI solution built on open data",
        subtitle="TED award notices and EU budget commitments, modelled in SQL Server, shaped in Power Query, analysed in DAX "
                 "and designed as a governed, accessible Power BI report.",
        tag="PUBLIC DATA + ONE SIMULATED PAGE", tag_class="real",
        kpis=[("Awards won", f"{k['awards']}", f"TED {y0}-{y1}, all entities and spellings resolved"),
              ("Buyers", f"{k['buyers']}", f"in {k['countries']} countries; {pct(k['repeat_rate'])} awarded more than once"),
              ("From EU institutions", pct(k["eu"]), "Commission DGs, agencies and other EU bodies"),
              ("EU budget commitments", f"€{k['fts'] / 1e6:,.0f}M", "FTS 2016-2025, European Commission, by year")],
        cols="1.05fr 1fr", rows="auto 1fr",
        cards=[card("Five questions, five short answers", qs, "1", "1 / span 2", text=True),
               card("Pipeline (one command per step, see README)", flow, "2", "1"),
               card("What the data suggest (and how the report handles it)", recs, "2", "2", text=True)],
        footer="Sources: TED (Publications Office of the EU), Financial Transparency System (European Commission), ECB, retrieved 15 Nov 2026"))

    # 1 ED in EU procurement --------------------------------------------------------
    facts = ("<p><span class='lab'>AS STATED BY EUROPEAN DYNAMICS</span> (eurodyn.com, read 15 Nov 2026)</p><ul>"
             "<li>Founded in <b>1993</b>; main development centre in Athens; offices or antennas in Athens, Berlin, Basel, "
             "Brussels, Copenhagen, Luxembourg, London, Milan, Nicosia, Vienna and others.</li>"
             "<li><b>Over 1,100</b> engineers, IT experts and consultants; clients: EU institutions and agencies, international "
             "organisations, national administrations.</li>"
             "<li>Focus on <b>e-Government</b> (e-procurement, customs, taxation, legislation publication...); certifications "
             "stated: ISO 9001, ISO/IEC 27001, ISO 22301, ISO/IEC 20000-1, ISO 14001, ISO 37001.</li></ul>"
             "<p><a href='https://www.eurodyn.com/company/who-we-are/'>eurodyn.com/company/who-we-are</a> · "
             "<a href='https://www.eurodyn.com/company/quality-and-security/'>/quality-and-security</a></p>"
             f"<p><span class='lab'>IN TED</span> &nbsp;{k['entities']} legal entities and labels (Greece, Luxembourg, Belgium, "
             f"Germany, UK, Switzerland, consortia) under {names} spellings. {pct(k['consortium'])} of awards are won with partners "
             f"outside the group, {pct(k['framework'])} are framework agreements.</p>")
    pages.append(dict(
        title=f"{k['awards']} awards from {k['buyers']} buyers since {y0}: EU institutions give {pct(k['eu'])} of them, "
              f"national administrations the rest",
        subtitle=f"About {first3:.0f} awards a year in {y0}-{y0 + 2}, {last3:.0f} in {y1 - 3}-{y1 - 1}. Buyer country is where the "
                 "contracting authority sits: Lisbon-based EU agencies count for Portugal, most institutions for Belgium and "
                 "Luxembourg. *2026 runs to 13 November.",
        tag="PUBLIC DATA · TED", tag_class="real", cols="1fr 1fr 0.9fr", rows="1fr 1fr",
        cards=[card("Awards per year, by buyer segment", pbi(1, C.awards_by_year(yr, 640, 300)), "1 / span 2", "1"),
               card("Published company facts", facts, "3", "1 / span 2", text=True),
               card("Top buyer groups (awards)", C.hbar(grp.g.tolist(), grp.n.tolist(), 430, 300), "1", "2"),
               card("Buyer country (awards)", C.hbar(ctry.CountryName.tolist(), ctry.n.tolist(), 420, 270), "2", "2")],
        footer="TED CAN CSV 2016-2023 + eForms XML 2023-2026 · one award = notice x lot x winning tender · page 1-2 of the Power BI report"))

    # 2 Domains, competition, market --------------------------------------------------
    best = ml["models"][ml["best_model"]]
    pages.append(dict(
        title=f"IT services dominate; European Dynamics holds {pct(k['share_n'], 1)} of the CPV 72 lots of its buyers and EU "
              f"institutions, with fewer single-offer lots than the comparison ({pct(k['so_ed'])} vs {pct(k['so_mkt'])})",
        subtitle=f"Lots won by European Dynamics drew {k['of_ed']:.1f} offers on average ({k['of_mkt']:.1f} for the other lots). A single "
                 f"offer is not an anomaly in itself: the model below (AUC {best['roc_auc']:.2f}) shows that the procedure type "
                 "explains most of it - negotiated procedures are often single-offer by design.",
        tag="PUBLIC DATA · TED · ML", tag_class="real", cols="1fr 1fr 1fr", rows="1fr 1fr",
        cards=[card("Domains: CPV classes of the awards", C.hbar(cls.d.tolist(), cls.n.tolist(), 430, 290), "1", "1"),
               card("Single-offer share by procedure: ED lots vs other lots",
                    C.paired_bars(proc.f.tolist(), proc.ed.tolist(), proc.mk.tolist(), "European Dynamics lots", "Other lots", 470, 270), "2", "1"),
               card("Share of CPV 72 lots, by year", C.share_line(share.Year.tolist(), share.s.tolist(), 470, 260), "3", "1"),
               card(f"What predicts a single offer? Permutation importance ({ml['rows']:,} IT lots)",
                    C.hbar(fi.feature.tolist(), fi.importance.round(3).tolist(), 470, 270, fmt="{:.3f}", color=C.GRAY_D), "1", "2"),
               card("Model card", "<ul>"
                    f"<li><b>Target</b>: lot received one offer ({pct(ml['single_offer_rate'])} of {ml['rows']:,} CPV 72 lots).</li>"
                    "<li><b>Features</b>: procedure, framework, buyer type and country, CPV group, log value, year, TED format.</li>"
                    "<li><b>Prep</b>: imputation, one-hot (rare levels grouped), scaling.</li>"
                    f"<li><b>Result</b> (5-fold CV): gradient boosting AUC {best['roc_auc']:.2f} ± {best['roc_auc_sd']:.2f}, "
                    f"logistic regression {ml['models']['Logistic regression']['roc_auc']:.2f}.</li>"
                    "<li><b>Limits</b>: notices are not independent (same buyers), offers missing on part of the notices, eForms "
                    "market at notice level; describes patterns, judges no procurement.</li></ul>", "2", "2", text=True),
               card("Other frequent winners at the same buyers (CPV 72)",
                    "<p>Listed without judgement, by number of buyers in common:</p>" +
                    table(competitors.rename(columns={"w": "Supplier", "b": "Buyers"}), num=("Buyers",)) +
                    "<p style='margin-top:6px'>Names kept only when they are companies (legal form found).</p>", "3", "2", text=True)],
        footer="Market context = CPV 72 awards of the same buyers + all EU institutions · scikit-learn, src/ml_single_offer.py · page 3 of the Power BI report"))

    # 3 FTS ----------------------------------------------------------------------------
    says = ("<p><span class='lab'>WHAT FTS SAYS</span></p><ul>"
            "<li>Legal commitments made each year by the European Commission (direct management) to European Dynamics "
            "entities, with the beneficiary's own share, the department, programme and type of contract.</li>"
            f"<li>{pct(ftype.s)} of the amount is classed as <i>{ftype.t}</i>.</li></ul>"
            "<p><span class='lab'>WHAT IT DOES NOT SAY</span></p><ul>"
            "<li>Not cash paid in the year: the estimated consumed amount is a separate, provisional figure (low for 2024 as published).</li>"
            "<li>No national contracts, no contracts of other EU institutions and agencies with their own budget (Parliament, "
            "agencies...): TED and FTS overlap only in part.</li>"
            "<li>Consortium commitments are attributed to the lead entity; amounts are as published, not audited.</li></ul>")
    pages.append(dict(
        title=f"The Commission committed €{k['fts'] / 1e6:,.0f}M to European Dynamics entities in 2016-2025; "
              f"{', '.join(dg.c.iloc[:3])} account for {pct(top3)}",
        subtitle="Financial Transparency System, yearly datasets. Amounts by year of commitment. Second data source of the model: "
                 "PostgreSQL design (script provided), read as CSV in this repository, cleaned and entity-matched in Power Query.",
        tag="PUBLIC DATA · FTS", tag_class="real", cols="1.25fr 1fr", rows="1.15fr 1fr",
        cards=[card("Committed and estimated consumed, by year (EUR million)", pbi(4, C.fts_years(fts, 700, 300)), "1", "1"),
               card("Committed by Commission department (EUR)", C.hbar(dg.c.tolist(), (dg.v / 1e6).round(1).tolist(), 520, 300, fmt="€{:,.1f}M"), "2", "1"),
               card("Reading FTS correctly", says, "1", "2", text=True),
               card("Committed by programme family (EUR)", C.hbar(prog.f.tolist(), (prog.v / 1e6).round(1).tolist(), 520, 260, fmt="€{:,.1f}M"), "2", "2")],
        footer="FTS (European Commission) 2016-2025, EN files, retrieved 15 Nov 2026 · DIGIT = Digital Services, JRC = Joint Research Centre, TAXUD = Taxation and Customs Union"))

    # 4 raw notices to star schema -----------------------------------------------------
    flow2 = ('<div class="flow">' + '<div class="a">→</div>'.join(
        f'<div class="s"><b>{a}</b>{b}</div>' for a, b in [
            ("Raw", "8 CSV years (4.5 GB), 160 XML,<br>API pages, 10 FTS files"),
            ("Python filter", "ED + CPV 72 context<br>no contact fields read"),
            ("stg (SQL Server)", "raw text, 1 table<br>per extract"),
            ("T-SQL ETL", "types, EUR, dedup,<br>name resolution"),
            ("dwh star", "6 dims, 2 facts<br>keys + indexes"),
            ("pbi views", "narrow, folding<br>→ Power Query")]) + "</div>")
    dq = ("<ul><li><b>Format change</b>: legacy CSV (award rows) vs eForms XML (parsed lot by lot).</li>"
          f"<li><b>{names} spellings</b> → {k['entities']} entities: LIKE patterns with priorities in SQL, fuzzy merge in Power Query.</li>"
          "<li><b>70 eForms rows excluded</b>: winner reference = the buyer's service provider (DQ-03/04).</li>"
          "<li><b>Frameworks</b>: value split equally between winning tenders, never double counted (check QA07).</li>"
          "<li><b>Non-Latin buyer names</b> lost by a first normaliser: found by a WARN check, fixed.</li>"
          "<li>Duplicates, outliers, missing currencies, joint procurement: see docs/DATA_QUALITY.md.</li></ul>")
    passed = int((qa.Status == "PASS").sum())
    pages.append(dict(
        title=f"From raw notices to a star schema: {k['rows_all']:,} award rows, {len(qa)} automated checks, {passed} pass",
        subtitle="SQL Server (LocalDB 2016 engine, same T-SQL as Express) holds a staging layer and a star schema; Power BI reads "
                 "narrow views through Power Query with query folding. Everything reruns from scripts.",
        tag="PUBLIC DATA · ENGINEERING", tag_class="real", cols="1.15fr 1fr", rows="auto 1fr 1fr",
        cards=[card(None, flow2, "1 / span 2", "1"),
               card("Model: star schema (Power BI)", C.star_schema(), "1", "2 / span 2"),
               card("Name resolution: typical hard spellings and their entity", table(names_tbl, num=("Rows",)), "2", "2", text=True),
               card("Issues found and how they were handled", dq, "2", "3", text=True)],
        footer="sql/01-07, src/build_dataset.py, src/load_sql.py · docs/DATA_DICTIONARY.md, docs/DATA_QUALITY.md"))

    # 5 DAX, performance, accessibility -------------------------------------------------
    m = {n: d for n, d, *_ in MEASURES}
    dax = (f"<pre class='dax'>ED Award Value =\n  {m['ED Award Value']}</pre>"
           f"<pre class='dax'>ED Single-Offer Share =\n  {m['ED Single-Offer Share'].replace(' ), CALCULATE', ' ),\n  CALCULATE')}</pre>"
           f"<pre class='dax'>ED Repeat Buyers =\n  {m['ED Repeat Buyers']}</pre>"
           f"<pre class='dax'>ED Share of CPV 72 Value =\n  {m['ED Share of CPV 72 Value']}</pre>"
           f"<pre class='dax'>ED Awards 3Y Moving Avg =\n  {m['ED Awards 3Y Moving Avg'].replace('RETURN', chr(10) + '  RETURN')}</pre>"
           "<pre class='dax'>-- calculation group 'Time Calc', item YoY %\nVAR cur = SELECTEDMEASURE ()\n"
           "VAR py  = CALCULATE ( SELECTEDMEASURE (), SAMEPERIODLASTYEAR ( DimDate[Date] ) )\n"
           "RETURN IF ( NOT ISBLANK ( py ), DIVIDE ( cur - py, py ) )</pre>")
    acc = ("<ul><li>Alt text on every data visual, describing what it shows and where the same numbers are readable.</li>"
           "<li>Tab order = reading order; same header, navigation and footer on every page.</li>"
           "<li>No information by colour alone: labels on bars, series named in titles and legends.</li>"
           "<li>Contrast: body text 19:1 and 7.8:1 on the page background; 11-26 pt text.</li>"
           "<li>Map doubled by a bar chart; SIMULATED page labelled in text, not colour.</li>"
           "<li>To verify in Desktop: screen-reader pass, keyboard navigation.</li></ul>")
    pages.append(dict(
        title=f"{len(MEASURES)} documented DAX measures and one calculation group; covering indexes cut the warehouse reads "
              f"for report queries from {pf.before.max()} to {pf.tuned.max()}",
        subtitle="Measures are plain SUMs over columns pre-computed in SQL (no double counting possible), CALCULATE adds the "
                 "business filter, DIVIDE guards zero. Time variants live once in a calculation group; a field parameter swaps axes.",
        tag="ENGINEERING", tag_class="", cols="1.2fr 1fr", rows="1fr 1fr",
        cards=[card("Key measures (all in docs/MEASURES.md, with examples)", dax, "1", "1 / span 2", text=True),
               card("SQL Server: logical reads per report-style query", C.perf(pf, 560, 250), "2", "1"),
               card("Accessibility checklist (docs/ACCESSIBILITY.md)", acc, "2", "2", text=True)],
        footer="src/build_tmdl.py (TMDL), src/perf_sql.py · first index set missed the summed column (key lookups): fixed, documented in docs/PERFORMANCE.md"))

    # 6 Governance ------------------------------------------------------------------------
    gov = ("<table><tr><th>Stage</th><th>Workspace</th><th>Who</th></tr>"
           "<tr><td>Dev</td><td>Procurement Analytics [Dev]</td><td>BI developers (Member / Contributor), git-synced</td></tr>"
           "<tr><td>Test</td><td>Procurement Analytics [Test]</td><td>business testers (Viewer), UAT</td></tr>"
           "<tr><td>Prod</td><td>Procurement Analytics</td><td>no manual edits; readers use the <b>app</b></td></tr></table>"
           "<p style='margin-top:8px'>Deployment pipeline Dev → Test → Prod with <b>deployment rules</b> on ServerName / DatabaseName; "
           "access through Entra <b>security groups</b>; two Admins; Build permission only for analysts; on-premises "
           "<b>gateway</b> for SQL Server and PostgreSQL; scheduled refresh after the ETL; <b>incremental refresh</b> on "
           "FactAward (the date filter folds to SQL).</p>"
           "<p><b>Dataflows</b>: dimensions, facts and FTS prepared once and shared; the M code in powerquery/ ports unchanged "
           "(parameters, folding, staging entity, explicit types).</p>"
           "<table style='margin-top:6px'><tr><th>Workspace role</th><th>Can</th><th>Given to (Entra groups)</th></tr>"
           "<tr><td>Admin</td><td>access, pipeline, delete</td><td>2 BI leads</td></tr>"
           "<tr><td>Member</td><td>publish, share, update the app</td><td>BI developers (Dev, Test)</td></tr>"
           "<tr><td>Contributor</td><td>create and edit content</td><td>report authors (Dev)</td></tr>"
           "<tr><td>Viewer</td><td>read, RLS applies</td><td>business testers (Test)</td></tr>"
           "<tr><td>App audience</td><td>read the published app, RLS applies</td><td>all production readers</td></tr></table>")
    rls = ("<pre class='dax'>role Agency (dynamic)\nDimAgency: [AgencyCode] IN CALCULATETABLE (\n    VALUES ( SecUserAgency[AgencyCode] ),\n"
           "    SecUserAgency[UserPrincipalName] = USERPRINCIPALNAME () )</pre>"
           "<p>Mapping table in the warehouse (a new user is a row). Test: <i>View as</i> → other user "
           "<span class='mono'>tax.lead@ministry.example</span> + role Agency → one agency; "
           "<span class='mono'>deputy.director@…</span> → two; role <i>Ministry (all agencies)</i> → six. Workspace Admins, "
           "Members and Contributors bypass RLS: readers get the app, not a role.</p>")
    pages.append(dict(
        title=f"Governance: Dev / Test / Prod workspaces, group-based access and row-level security, shown on a SIMULATED "
              f"service desk ({pct(k['sla'], 1)} of requests within SLA)",
        subtitle="The e-Government page uses invented data for a fictional ministry - not linked to European Dynamics or any "
                 "client - to demonstrate SLA measures and RLS by agency. Built as a Power BI project (TMDL + PBIR); Service "
                 "deployment documented in docs/SERVICE_DEPLOYMENT.md, not run on a tenant.",
        tag="SIMULATED (RLS PAGE)", tag_class="sim", cols="1.1fr 1fr", rows="1fr 1fr",
        cards=[card("Workspaces, roles, pipeline, refresh", gov, "1", "1 / span 2", text=True),
               card("SIMULATED: SLA met by agency (90% target)", pbi(5, C.sla(slag.n.tolist(), slag.s.tolist(), 0.9, 560, 250)), "2", "1"),
               card("Row-level security", rls, "2", "2", text=True)],
        footer="SIMULATED data: src/simulate_service_desk.py (seed 42), fictional .example accounts · page 5 of the Power BI report"))

    # 7 Methods, limits, AI note ------------------------------------------------------------
    src = ("<ul><li><b>TED</b>: Contract award notices CSV subset 2016-2023 (data.europa.eu, dataset ted-csv); Search API v3 and "
           "notice XML for eForms notices to 13 Nov 2026. (c) European Union, reuse with attribution (Decision 2011/833/EU).</li>"
           "<li><b>FTS</b>: European Commission, yearly datasets 2016-2025. Same reuse terms.</li>"
           "<li><b>ECB</b> euro reference rates (annual averages); <b>CPV 2008</b> list (TED).</li>"
           "<li><b>eurodyn.com</b>: company facts quoted as stated by European Dynamics.</li>"
           "<li>Collection: official endpoints only, one request per second, cached; retrieved 15 Nov 2026.</li></ul>")
    lim = ("<ul><li>Award values of frameworks are <b>ceilings</b>, not spending; the equal split is a convention.</li>"
           "<li>Only notices published in TED (above EU thresholds or voluntary); below-threshold national contracts are absent.</li>"
           "<li>Market context = same buyers + EU institutions, CPV 72 only; eForms context at notice level.</li>"
           "<li>Number of offers missing on part of the notices; buyer country = location of the buyer.</li>"
           "<li>FTS = Commission commitments only. 2026 partial.</li>"
           "<li>Power BI: built as TMDL + PBIR; Service deployment documented, not run on a tenant. PostgreSQL design "
           "provided, CSV fallback used.</li>"
           "<li>Neutral reading: one offer, repeat buyers or large frameworks are not anomalies in themselves.</li></ul>")
    meth = ("<p>T-SQL (CTE, window functions, set-based ETL), Power Query M (folding, fuzzy merge), DAX (CALCULATE, time "
            "intelligence, calculation group, field parameter, dynamic RLS), scikit-learn (gradient boosting, permutation "
            "importance), Python for collection and file generation, headless Edge for this PDF.</p>"
            "<p>Personal data: contact points, addresses, e-mails and phone numbers are never read; no employee is named.</p>"
            f"<div class='ai'>{AI_NOTE}</div>")
    rerun = ("<p><span class='mono'>python src/download_ted.py</span> → <span class='mono'>python src/download_fts.py</span> → "
             "<span class='mono'>python src/build_dataset.py</span> → <span class='mono'>python src/run_all.py</span> "
             "(simulation, SQL Server warehouse: sql/01-06 in order, ML, performance test, Power Query files, "
             "TMDL + PBIR, docs, notebook, this PDF). Then open <span class='mono'>powerbi/EuroDynProcurement.pbip</span> in "
             "Power BI Desktop and refresh; parameters ServerName / DatabaseName / DataFolder.</p>"
             "<p>Raw downloads (about 4.6 GB) stay in data/raw/ and are not versioned; the filtered extracts in "
             "data/processed/ are, so the warehouse and the report rebuild without downloading.</p>")
    nxt = ("<ul><li>Publish to a Dev workspace, run the deployment pipeline, schedule refresh through a gateway.</li>"
           "<li>Add contract notices (open tenders) to turn the history into a pipeline view.</li>"
           "<li>Report DQ-03 to the Publications Office.</li></ul>")
    pages.append(dict(
        title="Methods, sources and limits", subtitle=None, tag="", tag_class="", cols="1fr 1fr 1fr", rows="1fr auto",
        cards=[card("Sources and licences", src, "1", "1", text=True), card("Limits", lim, "2", "1", text=True),
               card("Methods & AI note", meth, "3", "1", text=True),
               card("How to rerun (Windows, Python 3.13, SQL Server LocalDB or Express)", rerun, "1 / span 2", "2", text=True),
               card("Next steps in a real project", nxt, "3", "2", text=True)],
        footer="Code: src/ · SQL: sql/ · Power Query: powerquery/ · model and report: powerbi/ · docs: docs/"))
    return pages


def edge() -> str:
    for p in (r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe", r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"):
        if Path(p).exists():
            return p
    return shutil.which("msedge") or "msedge"


def wait_file(path: Path, timeout=90):
    last, t0 = -1, time.time()
    while time.time() - t0 < timeout:
        if path.exists() and path.stat().st_size > 0 and path.stat().st_size == last:
            return
        last = path.stat().st_size if path.exists() else -1
        time.sleep(1.5)
    raise TimeoutError(f"{path} not produced")


def clean_pdf(path: Path):
    """Metadata reduced to the title: no author, tool or path."""
    from pypdf import PdfReader, PdfWriter
    r, w = PdfReader(str(path)), PdfWriter()
    for pg in r.pages:
        w.add_page(pg)
    w.add_metadata({"/Title": "European Dynamics in EU public procurement - Power BI case study"})
    for key in ("/Producer", "/Creator", "/Author"):
        w._info.get_object().pop(key, None)
    tmp = path.with_suffix(".tmp.pdf")
    with open(tmp, "wb") as fh:
        w.write(fh)
    tmp.replace(path)


def main():
    TMP.mkdir(exist_ok=True)
    (DOCS / "img").mkdir(parents=True, exist_ok=True)
    prof = TMP / "edge-profile"
    pages = build_pages()
    head = f"<!doctype html><html><head><meta charset='utf-8'><title>Case study</title><style>{CSS}</style></head><body>"
    sections = [PAGE.render(p=p, foot=FOOTER) for p in pages]
    src = TMP / "report.html"
    src.write_text(head + "".join(sections) + "</body></html>", encoding="utf-8")
    PDF.unlink(missing_ok=True)
    subprocess.run([edge(), "--headless=new", "--disable-gpu", "--no-pdf-header-footer", "--print-to-pdf-no-header",
                    f"--user-data-dir={prof}", f"--print-to-pdf={PDF}", src.as_uri()], check=True, capture_output=True, timeout=180)
    wait_file(PDF)
    clean_pdf(PDF)
    names = ["00_overview", "01_procurement", "02_domains_competition", "03_eu_budget", "04_star_schema",
             "05_dax_performance", "06_governance", "07_methods"]
    for name, sec in zip(names, sections):
        one = TMP / f"{name}.html"
        one.write_text(head.replace("page-break-after: always", "") + sec + "</body></html>", encoding="utf-8")
        out = DOCS / "img" / f"{name}.png"
        subprocess.run([edge(), "--headless=new", "--disable-gpu", "--hide-scrollbars", f"--user-data-dir={prof}",
                        "--window-size=1536,864", f"--screenshot={out}", one.as_uri()], check=True, capture_output=True, timeout=120)
        wait_file(out)
    print("PDF:", PDF.relative_to(ROOT), f"({PDF.stat().st_size // 1024} KB, {len(sections)} pages)")


if __name__ == "__main__":
    main()
