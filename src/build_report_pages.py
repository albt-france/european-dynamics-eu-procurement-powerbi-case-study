"""Generate the Power BI report pages (PBIR) of powerbi/EuroDynProcurement.Report.

Same page grammar as the earlier case studies: title = conclusion, grey subtitle, data tag (PUBLIC DATA /
SIMULATED) top right, footer with sources. Numbers in titles are read from the warehouse, never typed by hand.
Accessibility: every data visual gets alt text, tab order follows reading order (top-left to bottom-right),
titles say what to look at, and no information relies on colour alone (labels / legends everywhere).
5 report pages + a hidden documentation page + a tooltip page.
Usage:  python src/build_report_pages.py   (close Power BI Desktop first)
"""
import json
import shutil
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).parent))
from load_sql import connect, DATABASE  # noqa: E402

REPORT = ROOT / "powerbi" / "EuroDynProcurement.Report"
PAGES = REPORT / "definition" / "pages"
VC_SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/2.4.0/schema.json"
PAGE_SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/page/2.1.0/schema.json"
PAGES_SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/pagesMetadata/1.1.0/schema.json"
M = "_Measures"

INK, INK2, MUTED = "#0B0B0B", "#52514E", "#898781"
BLUE, GREY, LIGHT, ORANGE = "#2A78D6", "#B4B2A9", "#D3D1C7", "#EB6834"
AUTHOR = "Independent case study based on public data · not affiliated with or endorsed by European Dynamics"


# ---------------------------------------------------------------- figures for the titles (from the warehouse)
def facts():
    cn = connect(DATABASE)
    one = lambda sql: pd.read_sql(sql, cn).iloc[0].to_dict()  # noqa: E731
    f = one("""SELECT COUNT(*) awards, COUNT(DISTINCT BuyerKey) buyers, COUNT(DISTINCT CountryKey) countries,
                      MIN(LEFT(DateKey,4)) y0, MAX(LEFT(DateKey,4)) y1
               FROM dwh.FactAward WHERE IsED = 1""")
    f.update(one("""SELECT AVG(IIF(b.IsEU = 1, 1.0, 0.0)) eu_share FROM dwh.FactAward a JOIN dwh.DimBuyer b
                    ON b.BuyerKey = a.BuyerKey WHERE a.IsED = 1"""))
    f.update(one("""WITH b AS (SELECT BuyerKey, COUNT(*) n FROM dwh.FactAward WHERE IsED = 1 GROUP BY BuyerKey)
                    SELECT AVG(IIF(n >= 2, 1.0, 0.0)) repeat_rate FROM b"""))
    f.update(one("""SELECT SUM(IIF(a.IsED = 1, a.ValueSplitEUR, 0)) / SUM(a.ValueSplitEUR) cpv72_share,
                           SUM(IIF(a.IsED = 1, 1.0, 0)) / COUNT(*) cpv72_share_n
                    FROM dwh.FactAward a JOIN dwh.DimCPV c ON c.CpvKey = a.CpvKey WHERE c.IsITServices = 1"""))
    f.update(one("""SELECT AVG(IIF(IsED = 1, IIF(NumberOfOffers = 1, 1.0, 0.0), NULL)) so_ed,
                           AVG(IIF(IsED = 0, IIF(NumberOfOffers = 1, 1.0, 0.0), NULL)) so_mkt,
                           AVG(IIF(IsED = 1, CAST(NumberOfOffers AS FLOAT), NULL)) offers_ed,
                           AVG(IIF(IsED = 0, CAST(NumberOfOffers AS FLOAT), NULL)) offers_mkt
                    FROM dwh.FactAward WHERE NumberOfOffers IS NOT NULL"""))
    f.update(one("""SELECT AVG(IIF(c.IsITServices = 1, 1.0, 0.0)) it_share FROM dwh.FactAward a
                    JOIN dwh.DimCPV c ON c.CpvKey = a.CpvKey WHERE a.IsED = 1"""))
    f.update(one("""SELECT SUM(ContractedEUR) fts_total, SUM(IIF([Year] BETWEEN 2016 AND 2018, ContractedEUR, 0)) fts_1618,
                           SUM(IIF([Year] BETWEEN 2023 AND 2025, ContractedEUR, 0)) fts_2325
                    FROM dwh.FactFts WHERE [Year] <= 2025"""))
    f.update(one("""SELECT TOP 3 STUFF((SELECT TOP 3 ', ' + d.DepartmentCode FROM dwh.FactFts x JOIN dwh.DimDepartment d
                           ON d.DepartmentKey = x.DepartmentKey GROUP BY d.DepartmentCode ORDER BY SUM(x.ContractedEUR) DESC
                           FOR XML PATH('')), 1, 2, '') top_dgs"""))
    f.update(one("""WITH d AS (SELECT TOP 3 DepartmentKey, SUM(ContractedEUR) v FROM dwh.FactFts GROUP BY DepartmentKey ORDER BY v DESC)
                    SELECT (SELECT SUM(v) FROM d) / (SELECT SUM(ContractedEUR) FROM dwh.FactFts) top3_share"""))
    f.update(one("""SELECT AVG(IIF(IsSlaMet = 1, 1.0, 0.0)) sla FROM sim.FactServiceRequest WHERE IsClosed = 1"""))
    f.update(one("""SELECT TOP 1 a.AgencyName worst_agency, AVG(IIF(r.IsSlaMet = 1, 1.0, 0.0)) worst_sla
                    FROM sim.FactServiceRequest r JOIN sim.DimAgency a ON a.AgencyKey = r.AgencyKey
                    WHERE r.IsClosed = 1 GROUP BY a.AgencyName ORDER BY 2"""))
    ml = json.loads((ROOT / "data" / "processed" / "ml_metrics.json").read_text())
    f["ml_auc"] = ml["models"][ml["best_model"]]["roc_auc"]
    f["ml_rows"] = ml["rows"]
    return f


F = facts()


def pct(x, d=0):
    return f"{100 * x:.{d}f}%"


def eur_m(x):
    return f"EUR {x / 1e6:,.0f} million"


# ---------------------------------------------------------------- expression helpers (same as earlier studies)
def raw(v):
    if isinstance(v, bool):
        s = "true" if v else "false"
    elif isinstance(v, int):
        s = f"{v}L"
    elif isinstance(v, float):
        s = f"{v}D"
    else:
        s = "'" + str(v).replace("'", "''") + "'"
    return {"Literal": {"Value": s}}


def lit(v):
    if isinstance(v, int) and not isinstance(v, bool):
        v = float(v)
    return {"expr": raw(v)}


def color(hexv):
    return {"solid": {"color": lit(hexv)}}


def col(table, column):
    return {"Column": {"Expression": {"SourceRef": {"Entity": table}}, "Property": column}}


def meas(name):
    return {"Measure": {"Expression": {"SourceRef": {"Entity": M}}, "Property": name}}


def agg(table, column, fn=0):
    return {"Aggregation": {"Expression": col(table, column), "Function": fn}}


def qref(field):
    if "Column" in field:
        c = field["Column"]
        return f'{c["Expression"]["SourceRef"]["Entity"]}.{c["Property"]}'
    if "Measure" in field:
        return f'{M}.{field["Measure"]["Property"]}'
    c = field["Aggregation"]["Expression"]["Column"]
    fn = "Sum" if field["Aggregation"]["Function"] == 0 else "Avg"
    return f'{fn}({c["Expression"]["SourceRef"]["Entity"]}.{c["Property"]})'


def proj(field, label=None):
    p = {"field": field, "queryRef": qref(field)}
    if "Column" in field:
        p["nativeQueryRef"] = field["Column"]["Property"]
    elif "Measure" in field:
        p["nativeQueryRef"] = field["Measure"]["Property"]
    else:
        p["nativeQueryRef"] = field["Aggregation"]["Expression"]["Column"]["Property"]
    if label:
        p["displayName"] = label
    return p


def C(t, c):
    return col(t, c)


def Ms(*names):
    return [meas(n) for n in names]


def series_color(field, hexv):
    return {"properties": {"fill": color(hexv)}, "selector": {"metadata": qref(field)}}


def table_style(matrix=False, font=12):
    fs = {"properties": {"fontSize": lit(font)}}
    objs = {"values": [fs], "columnHeaders": [{"properties": {"fontSize": lit(font), "fontColor": color(INK2)}}]}
    if matrix:
        objs["rowHeaders"] = [fs]
        objs["subTotals"] = [{"properties": {"rowSubtotals": lit(False), "columnSubtotals": lit(False)}}]
    else:
        objs["total"] = [{"properties": {"totals": lit(False)}}]
    return objs


def data_labels(fmt_color=INK):
    return [{"properties": {"show": lit(True), "color": color(fmt_color)}}]


def flt(table, column, values, negate=False):
    return (table, column, values, negate)


def slicer_selection(table, column, value):
    return {"filter": {"filter": {"Version": 2, "From": [{"Name": "s", "Entity": table, "Type": 0}],
                                  "Where": [{"Condition": {"In": {
                                      "Expressions": [{"Column": {"Expression": {"SourceRef": {"Source": "s"}}, "Property": column}}],
                                      "Values": [[raw(value)]]}}}]}}}


# ---------------------------------------------------------------- page / visual builders
class Page:
    def __init__(self, pid, name, hidden=False, tooltip=False):
        self.pid, self.name, self.visuals, self.n = pid, name, [], 0
        self.hidden, self.tooltip = hidden, tooltip

    def _add(self, vid, x, y, w, h, visual, alt=None):
        self.n += 1
        if alt:
            visual.setdefault("visualContainerObjects", {})["general"] = [{"properties": {"altText": lit(alt)}}]
        self.visuals.append({"$schema": VC_SCHEMA, "name": vid,
                             "position": {"x": round(x), "y": round(y), "z": self.n * 1000,
                                          "height": round(h), "width": round(w), "tabOrder": self.n * 1000},
                             "visual": visual})
        return vid

    def chart(self, vid, vtype, x, y, w, h, roles, title=None, objects=None, labels=None, sort=None, filters=(),
              alt=None, tooltip_page=None):
        labels = labels or {}
        visual = {"visualType": vtype,
                  "query": {"queryState": {r: {"projections": [proj(f, labels.get(qref(f))) for f in fs]}
                                           for r, fs in roles.items() if fs}},
                  "drillFilterOtherVisuals": True}
        if sort:
            field, direction = sort
            visual["query"]["sortDefinition"] = {"sort": [{"field": field, "direction": direction}], "isDefaultSort": False}
        objects = dict(objects or {})
        if tooltip_page:
            objects["tooltips"] = [{"properties": {"type": lit("ReportPage"), "section": lit(tooltip_page)}}]
        if objects:
            visual["objects"] = objects
        vco = {"subTitle": [{"properties": {"show": lit(False)}}],
               "title": [{"properties": {"show": lit(bool(title)), **({"text": lit(title)} if title else {})}}]}
        visual["visualContainerObjects"] = vco
        self._add(vid, x, y, w, h, visual, alt or title)
        fl = []
        for i, (table, column, values, negate) in enumerate(filters):
            cond = {"In": {"Expressions": [{"Column": {"Expression": {"SourceRef": {"Source": "t"}}, "Property": column}}],
                           "Values": [[raw(v)] for v in values]}}
            if negate:
                cond = {"Not": {"Expression": cond}}
            fl.append({"name": f"visualFilter{i}", "type": "Categorical", "field": col(table, column),
                       "filter": {"Version": 2, "From": [{"Name": "t", "Entity": table, "Type": 0}],
                                  "Where": [{"Condition": cond}]}})
        if fl:
            self.visuals[-1]["filterConfig"] = {"filters": fl}
        return vid

    def text(self, vid, x, y, w, h, paragraphs, boxed=False):
        paras = [{"textRuns": [{"value": t, "textStyle": {"fontSize": f"{s}pt", "color": c,
                                                         **({"fontWeight": "bold"} if b else {})}}
                               for t, s, c, b in runs]} for runs in paragraphs]
        visual = {"visualType": "textbox",
                  "objects": {"general": [{"properties": {"paragraphs": paras}}]},
                  "visualContainerObjects": {"background": [{"properties": {"show": lit(boxed)}}],
                                             "border": [{"properties": {"show": lit(boxed)}}],
                                             **({"padding": [{"properties": {"top": lit(14), "bottom": lit(14),
                                                                             "left": lit(18), "right": lit(18)}}]}
                                                if boxed else {})}}
        return self._add(vid, x, y, w, h, visual)

    def header(self, title, conclusion, tag):
        self.text("title", 32, 16, 1500, 56, [[(title, 22, INK, True)]])
        self.text("tag", 1560, 22, 328, 40, [[(tag, 10, INK2, True)]])
        self.text("conclusion", 32, 70, 1856, 56, [[(conclusion, 12, INK2, False)]])
        self.navigator()

    def navigator(self):
        visual = {"visualType": "pageNavigator", "objects": {}, "visualContainerObjects": {
            "title": [{"properties": {"show": lit(False)}}]}}
        self._add("navigator", 32, 124, 1856, 40, visual, "Page navigation buttons")

    def footer(self, source):
        self.text("footer", 32, 1040, 1856, 32, [[(source + "   ·   " + AUTHOR, 9, MUTED, False)]])

    def slicer(self, vid, x, y, w, h, field, title, dropdown=True, single=False, selected=None):
        objs = {"header": [{"properties": {"show": lit(True)}}]}
        if dropdown:
            objs["data"] = [{"properties": {"mode": lit("Dropdown")}}]
        if single:
            objs["selection"] = [{"properties": {"singleSelect": lit(True), "strictSingleSelect": lit(True)}}]
        if selected:
            objs["general"] = [{"properties": slicer_selection(*selected)}]
        return self.chart(vid, "slicer", x, y, w, h, {"Values": [field]}, title, objs, alt=f"Filter: {title}")

    def card(self, vid, x, y, w, h, measure, title):
        return self.chart(vid, "card", x, y, w, h, {"Values": [meas(measure)]}, title,
                          {"labels": [{"properties": {"color": color(INK), "fontSize": lit(26)}}],
                           "categoryLabels": [{"properties": {"show": lit(False)}}]}, alt=f"{title} (card)")

    def write(self):
        d = PAGES / self.pid
        if d.exists():
            shutil.rmtree(d)
        (d / "visuals").mkdir(parents=True)
        page = {"$schema": PAGE_SCHEMA, "name": self.pid, "displayName": self.name,
                "displayOption": "FitToPage", "height": 1080, "width": 1920}
        if self.tooltip:
            page.update({"height": 320, "width": 480, "displayOption": "ActualSize",
                         "pageBinding": {"name": "tt_" + self.pid, "type": "Tooltip", "parameters": []}})
        if self.hidden or self.tooltip:
            page["visibility"] = "HiddenInViewMode"
        (d / "page.json").write_text(json.dumps(page, indent=2, ensure_ascii=False), encoding="utf-8")
        for v in self.visuals:
            vd = d / "visuals" / v["name"]
            vd.mkdir()
            (vd / "visual.json").write_text(json.dumps(v, indent=2, ensure_ascii=False), encoding="utf-8")


# ---------------------------------------------------------------- layout grid
L, R, TOP, BOT, GAP = 32, 1888, 180, 1028, 20
W = R - L


def cols(n, x0=L, x1=R):
    w = (x1 - x0 - (n - 1) * GAP) / n
    return [(x0 + i * (w + GAP), w) for i in range(n)]


def kpi_row(p, items, y=TOP, h=110, x0=L, x1=R):
    for (x, w), (m, t) in zip(cols(len(items), x0, x1), items):
        p.card("kpi_" + "".join(ch for ch in m if ch.isalnum())[:30], x, y, w, h, m, t)
    return y + h + GAP


TT = "f9000000000000000009"     # tooltip page id
pages = []
YEAR, AXISF = C("DimDate", "Year"), C("Axis", "Axis")

# ======================= 1. Overview =======================
p = Page("f1000000000000000001", "Overview")
p.header(f"European Dynamics won {F['awards']} published EU-procurement awards from {F['buyers']} buyers since "
         f"{F['y0']}; {pct(F['eu_share'])} came from EU institutions and agencies",
         f"TED award notices {F['y0']}-{F['y1']} (legacy CSV to Oct 2023, eForms after), all entities and spellings resolved. "
         f"The Commission's Financial Transparency System adds {eur_m(F['fts_total'])} of legal commitments 2016-2025. "
         "Award values of framework agreements are ceilings shared between winners, so counts lead and values follow.",
         "PUBLIC DATA · TED + FTS")
y = kpi_row(p, [("ED Awards", "Awards won (rows)"), ("ED Buyers", "Distinct buyers"), ("ED Countries", "Buyer countries"),
                ("ED Share from EU Institutions", "From EU institutions"), ("FTS Contracted", "EU budget commitments (FTS)")])
(xa, wa), (xb, wb) = cols(2)
h1 = (BOT - y - GAP) * 0.55
p.chart("combo_year", "lineClusteredColumnComboChart", xa, y, wa, h1,
        {"Category": [YEAR], "Y": Ms("ED Awards"), "Y2": Ms("ED Awards 3Y Moving Avg")},
        "Awards per year, with 3-year moving average",
        {"dataPoint": [series_color(meas("ED Awards"), BLUE)], "labels": data_labels()},
        alt="Column chart of European Dynamics awards per year 2016-2026 with a line for the 3-year moving average. "
            "2026 is partial (to mid-November).", tooltip_page=None)
p.chart("map_buyers", "map", xb, y, wb, h1,
        {"Category": [C("DimCountry", "CountryName")], "Size": Ms("ED Awards")},
        "Where the buyers are (bubble size = awards)",
        alt="Map of buyer countries, bubble size proportional to European Dynamics awards. EU agencies count in their "
            "host country (e.g. Portugal for Lisbon-based agencies). Same figures in the bar chart below.")
y2 = y + h1 + GAP
p.chart("bar_country", "clusteredBarChart", xa, y2, wa, BOT - y2,
        {"Category": [C("DimCountry", "CountryName")], "Y": Ms("ED Awards")}, "Awards by buyer country",
        {"labels": data_labels(), "dataPoint": [series_color(meas("ED Awards"), BLUE)]},
        sort=(meas("ED Awards"), "Descending"), tooltip_page=TT)
p.chart("mx_timecalc", "pivotTable", xb, y2, wb, BOT - y2,
        {"Rows": [YEAR], "Columns": [C("Time Calc", "Period")], "Values": Ms("ED Awards")},
        "Calculation group: one measure, six time variants", table_style(matrix=True, font=11),
        filters=[flt("Time Calc", "Period", ["Selected period", "Previous year", "YoY %", "3-year total"])],
        alt="Matrix: years in rows, time variants (selected period, previous year, YoY %, 3-year total) in columns.")
p.footer("TED (Publications Office): CAN CSV subsets 2016-2023 + Search API v3 / eForms XML 2023-2026, retrieved 15 Nov 2026 · "
         "FTS (European Commission) 2016-2025")
pages.append(p)

# ======================= 2. Buyers & countries =======================
p = Page("f2000000000000000002", "Buyers & countries")
p.header(f"Repeat business: {pct(F['repeat_rate'])} of buyers awarded European Dynamics more than once",
         "EU institutions (Commission DGs, agencies) and national administrations behave differently: few large "
         "framework buyers at EU level, many smaller national buyers. Use the axis selector (field parameter) to "
         "switch the comparison; hover a bar for the buyer tooltip.",
         "PUBLIC DATA · TED")
c3 = cols(3)
p.slicer("sl_segment", c3[0][0], TOP, c3[0][1], 70, C("DimBuyer", "BuyerSegment"), "Buyer segment")
p.slicer("sl_axis", c3[1][0], TOP, c3[1][1], 70, AXISF, "Compare by (field parameter)", single=True,
         selected=("Axis", "Axis", "Buyer segment"))
p.slicer("sl_year", c3[2][0], TOP, c3[2][1], 70, YEAR, "Year")
y = TOP + 70 + GAP
y = kpi_row(p, [("ED Buyers", "Buyers"), ("ED Repeat Buyers", "Repeat buyers (2+ awards)"),
                ("ED Repeat Buyer Rate", "Repeat buyer rate"), ("ED Median Award Value", "Median award value (split)")], y=y)
(xa, wa), (xb, wb) = cols(2)
h1 = (BOT - y - GAP) / 2
p.chart("bar_axis", "clusteredBarChart", xa, y, wa, h1, {"Category": [AXISF], "Y": Ms("ED Awards", "ED Buyers")},
        "Awards and buyers by the selected axis",
        {"labels": data_labels(), "dataPoint": [series_color(meas("ED Awards"), BLUE), series_color(meas("ED Buyers"), GREY)]},
        alt="Bar chart of awards and distinct buyers by the axis chosen in the 'Compare by' slicer.")
p.chart("bar_buyers", "clusteredBarChart", xb, y, wb, h1, {"Category": [C("DimBuyer", "BuyerName")], "Y": Ms("ED Awards")},
        "Buyers ranked by awards (scroll for more)", {"labels": data_labels(), "dataPoint": [series_color(meas("ED Awards"), BLUE)]},
        sort=(meas("ED Awards"), "Descending"), tooltip_page=TT)
p.chart("decomp", "decompositionTreeVisual", xa, y + h1 + GAP, wa, BOT - (y + h1 + GAP),
        {"Analyze": Ms("ED Awards"), "ExplainBy": [C("DimBuyer", "BuyerSegment"), C("DimBuyer", "BuyerGroup"),
                                                   C("DimCountry", "CountryName"), C("DimEntity", "EntityName"),
                                                   C("DimProcedure", "ProcedureFamily")]},
        "AI visual - decomposition tree: drill awards by segment, buyer group, country, entity, procedure",
        alt="Decomposition tree (Power BI AI visual) splitting European Dynamics awards by buyer segment, buyer group, "
            "country, entity and procedure.")
p.chart("tbl_buyers", "tableEx", xb, y + h1 + GAP, wb, BOT - (y + h1 + GAP),
        {"Values": [C("DimBuyer", "BuyerName"), C("DimBuyer", "BuyerType"), meas("ED Awards"), meas("ED Award Value"),
                    meas("ED Avg Offers")]}, "Buyer detail", table_style(font=11),
        sort=(meas("ED Awards"), "Descending"))
p.footer("TED award notices 2016-2026 · buyer = contracting authority as published (lead buyer for joint procurement), names normalised in SQL")
pages.append(p)

# ======================= 3. Domains & competition =======================
p = Page("f3000000000000000003", "Domains & competition")
p.header(f"{pct(F['it_share'])} of the awards are IT services (CPV 72), where European Dynamics holds "
         f"{pct(F['cpv72_share_n'], 1)} of the lots of its own buyers and EU institutions",
         f"Lots won by European Dynamics received {F['offers_ed']:.1f} offers on average ({F['offers_mkt']:.1f} for the "
         f"comparison lots); {pct(F['so_ed'])} received a single offer ({pct(F['so_mkt'])} for the others). A single offer "
         f"is not an anomaly in itself: the ML model (AUC {F['ml_auc']:.2f}) shows that the procedure type explains most of it.",
         "PUBLIC DATA · TED · ML")
y = kpi_row(p, [("ED Share of CPV 72 Awards", "Share of CPV 72 lots"), ("ED Share of CPV 72 Value", "Share of CPV 72 value (split)"),
                ("ED Avg Offers", "Avg offers, ED lots"), ("Market Avg Offers", "Avg offers, other lots"),
                ("ED Single-Offer Share", "Single offer, ED lots"), ("Market Single-Offer Share", "Single offer, other lots")])
(xa, wa), (xb, wb) = cols(2)
h1 = (BOT - y - GAP) / 2
p.chart("bar_cpv", "clusteredBarChart", xa, y, wa, h1, {"Category": [C("DimCPV", "Division")], "Y": Ms("ED Awards")},
        "Awards by CPV division (domain)", {"labels": data_labels(), "dataPoint": [series_color(meas("ED Awards"), BLUE)]},
        sort=(meas("ED Awards"), "Descending"))
p.chart("bar_proc", "clusteredBarChart", xb, y, wb, h1,
        {"Category": [C("DimProcedure", "ProcedureFamily")], "Y": Ms("ED Single-Offer Share", "Market Single-Offer Share")},
        "Single-offer share by procedure family: ED lots vs other lots",
        {"labels": data_labels(), "dataPoint": [series_color(meas("ED Single-Offer Share"), BLUE),
                                                series_color(meas("Market Single-Offer Share"), GREY)]},
        alt="Bar chart comparing the single-offer share of European Dynamics lots (blue) and other lots (grey) for each "
            "procedure family; values are labelled.")
p.chart("line_share", "lineChart", xa, y + h1 + GAP, wa * 0.5 - GAP / 2, BOT - (y + h1 + GAP),
        {"Category": [YEAR], "Y": Ms("ED Share of CPV 72 Awards")}, "Share of CPV 72 lots per year",
        {"labels": data_labels(), "dataPoint": [series_color(meas("ED Share of CPV 72 Awards"), BLUE)]})
p.chart("tbl_ml", "tableEx", xa + wa * 0.5 + GAP / 2, y + h1 + GAP, wa * 0.5 - GAP / 2, BOT - (y + h1 + GAP),
        {"Values": [C("ML Metrics", "Metric"), C("ML Metrics", "Display")]},
        "ML model: will an IT lot get one offer?", table_style(font=11), labels={"ML Metrics.Display": "Value"})
p.chart("bar_ml", "clusteredBarChart", xb, y + h1 + GAP, wb, BOT - (y + h1 + GAP),
        {"Category": [C("ML Feature Importance", "Feature")], "Y": [agg("ML Feature Importance", "Importance")]},
        f"What predicts a single offer (permutation importance, {F['ml_rows']:,} IT lots)",
        {"labels": data_labels(), "dataPoint": [series_color(agg("ML Feature Importance", "Importance"), GREY)]},
        sort=(agg("ML Feature Importance", "Importance"), "Descending"),
        labels={"Sum(ML Feature Importance.Importance)": "Drop in ROC AUC"})
p.footer("TED award notices · CPV 2008 labels (TED) · offers = number of tenders received as published · model: "
         "scikit-learn gradient boosting, 5-fold CV, src/ml_single_offer.py")
pages.append(p)

# ======================= 4. EU budget (FTS) =======================
p = Page("f4000000000000000004", "EU budget (FTS)")
p.header(f"Commission commitments to European Dynamics rose from {eur_m(F['fts_1618'])} in 2016-2018 to "
         f"{eur_m(F['fts_2325'])} in 2023-2025; {F['top_dgs']} account for {pct(F['top3_share'])}",
         "FTS lists legal commitments made each year by the Commission (direct management), with the beneficiary's "
         "share. They are not cash payments and do not cover national contracts or other EU institutions' own budgets. "
         "Second data source of the model (PostgreSQL design, CSV fallback here), shaped in Power Query.",
         "PUBLIC DATA · FTS")
y = kpi_row(p, [("FTS Contracted", "Committed (contracted)"), ("FTS Est. Consumed", "Estimated consumed"),
                ("FTS Consumption Rate", "Consumed / committed"), ("FTS Top Department Share", "Largest department share"),
                ("FTS Departments", "Commission departments")])
(xa, wa), (xb, wb) = cols(2)
h1 = (BOT - y - GAP) / 2
p.chart("col_fts_year", "clusteredColumnChart", xa, y, wa, h1, {"Category": [YEAR], "Y": Ms("FTS Contracted", "FTS Est. Consumed")},
        "Committed and estimated consumed amounts by year",
        {"labels": data_labels(), "dataPoint": [series_color(meas("FTS Contracted"), BLUE), series_color(meas("FTS Est. Consumed"), GREY)]},
        alt="Column chart by year of commitment: committed amount (blue) and estimated consumed amount (grey), labelled in EUR millions.")
p.chart("bar_dept", "clusteredBarChart", xb, y, wb, BOT - y, {"Category": [C("DimDepartment", "Department")], "Y": Ms("FTS Contracted")},
        "Commitments by Commission department", {"labels": data_labels(), "dataPoint": [series_color(meas("FTS Contracted"), BLUE)]},
        sort=(meas("FTS Contracted"), "Descending"))
p.chart("bar_prog", "clusteredBarChart", xa, y + h1 + GAP, wa * 0.5 - GAP / 2, BOT - (y + h1 + GAP),
        {"Category": [C("DimProgramme", "ProgrammeFamily")], "Y": Ms("FTS Contracted")}, "By programme family",
        {"labels": data_labels(), "dataPoint": [series_color(meas("FTS Contracted"), BLUE)]}, sort=(meas("FTS Contracted"), "Descending"))
p.chart("tbl_type", "tableEx", xa + wa * 0.5 + GAP / 2, y + h1 + GAP, wa * 0.5 - GAP / 2, BOT - (y + h1 + GAP),
        {"Values": [C("FactFts", "ContractType"), meas("FTS Contracted")]}, "By type of contract", table_style(font=11),
        sort=(meas("FTS Contracted"), "Descending"))
p.footer("Financial Transparency System, European Commission, yearly datasets 2016-2025 (EN), retrieved 15 Nov 2026 · "
         "entities resolved with a fuzzy merge in Power Query (threshold 0.8)")
pages.append(p)

# ======================= 5. e-Government service desk (SIMULATED) =======================
p = Page("f5000000000000000005", "e-Gov service desk (SIMULATED)")
p.header(f"SIMULATED: {pct(F['sla'], 1)} of requests met their SLA; {F['worst_agency']} is the weakest at "
         f"{pct(F['worst_sla'], 1)}",
         "Fictional ministry and agencies, invented data, not linked to European Dynamics or any client. The page shows "
         "SLA measures and row-level security: role 'Agency' filters DimAgency with USERPRINCIPALNAME(); test it with "
         "Modeling > View as > Other user (e.g. tax.lead@ministry.example) + role Agency.",
         "SIMULATED DATA · RLS DEMO")
p.card("kpi_label", L, TOP, W, 70, "Visible Agencies Label", "Row-level security check")
y = kpi_row(p, [("Requests", "Requests"), ("SLA Met %", "SLA met"), ("SLA Gap vs 90% Target", "Gap vs 90% target"),
                ("Median Resolution (h)", "Median resolution (h)"), ("P90 Resolution (h)", "P90 resolution (h)"),
                ("Open Backlog", "Open backlog"), ("Avg Satisfaction", "Satisfaction (1-5)")], y=TOP + 70 + GAP)
(xa, wa), (xb, wb) = cols(2)
h1 = (BOT - y - GAP) / 2
p.chart("line_daily", "lineChart", xa, y, W, h1, {"Category": [C("DimDate", "Date")], "Y": Ms("Requests")},
        "Daily requests (AI: anomaly detection on the line)",
        {"dataPoint": [series_color(meas("Requests"), BLUE)],
         "anomalyDetection": [{"properties": {"show": lit(True), "sensitivity": lit(80)},
                               "selector": {"metadata": qref(meas("Requests"))}}]},
        filters=[flt("DimDate", "Year", [2025, 2026])],
        alt="Line chart of daily SIMULATED requests in 2025-2026 with Power BI anomaly detection highlighting unusual days.")
p.chart("bar_agency", "clusteredBarChart", xa, y + h1 + GAP, wa, BOT - (y + h1 + GAP),
        {"Category": [C("DimAgency", "AgencyName")], "Y": Ms("SLA Met %")}, "SLA met by agency (90% target)",
        {"labels": data_labels(), "dataPoint": [series_color(meas("SLA Met %"), BLUE)]}, sort=(meas("SLA Met %"), "Ascending"))
p.chart("mx_priority", "pivotTable", xb, y + h1 + GAP, wb, BOT - (y + h1 + GAP),
        {"Rows": [C("DimAgency", "AgencyName")], "Columns": [C("FactServiceRequest", "Priority")],
         "Values": Ms("SLA Met %")}, "SLA met by agency and priority", table_style(matrix=True, font=12))
p.footer("SIMULATED data generated by src/simulate_service_desk.py (seed 42) · fictional .example accounts in SecUserAgency")
pages.append(p)

# ======================= 6. Model documentation (hidden) =======================
p = Page("f6000000000000000006", "Model documentation", hidden=True)
p.header("Model documentation: star schema, data quality checks and name resolution",
         "Hidden page for maintainers. FactAward (TED) and FactFts (FTS) share DimDate and DimEntity; the SIMULATED "
         "service desk has its own fact and agency dimension. All relationships are one-to-many, single direction. "
         "Measures live in _Measures, grouped in display folders, each with a description.", "DOCUMENTATION")
(xa, wa), (xb, wb) = cols(2)
p.chart("tbl_qa", "tableEx", xa, TOP, wa, BOT - TOP,
        {"Values": [C("QualityChecks", "CheckId"), C("QualityChecks", "CheckName"), C("QualityChecks", "Actual"),
                    C("QualityChecks", "Status")]}, "Data-quality checks (sql/06_quality_checks.sql)", table_style(font=11))
p.chart("tbl_names", "tableEx", xb, TOP, wb, BOT - TOP,
        {"Values": [C("EntityNameMap", "RawName"), C("EntityNameMap", "EntityName"), C("EntityNameMap", "SourceSystem"),
                    agg("EntityNameMap", "Occurrences")]},
        "Name resolution: raw spelling -> entity", table_style(font=10), sort=(agg("EntityNameMap", "Occurrences"), "Descending"))
p.footer("sql/02_reference_data.sql (alias patterns) · sql/04_etl_load_dwh.sql (resolution) · docs/DATA_DICTIONARY.md")
pages.append(p)

# ======================= 7. Tooltip page =======================
p = Page(TT, "Tooltip - buyer", tooltip=True)
p.card("tt_awards", 10, 10, 150, 90, "ED Awards", "Awards")
p.card("tt_value", 165, 10, 150, 90, "ED Award Value", "Value (split)")
p.card("tt_offers", 320, 10, 150, 90, "ED Avg Offers", "Avg offers")
p.chart("tt_year", "clusteredColumnChart", 10, 110, 460, 200, {"Category": [YEAR], "Y": Ms("ED Awards")}, "Awards per year",
        {"dataPoint": [series_color(meas("ED Awards"), BLUE)]})
pages.append(p)

# ---------------------------------------------------------------- write
PAGES.mkdir(parents=True, exist_ok=True)
keep = {pg.pid for pg in pages}
for d in PAGES.iterdir():
    if d.is_dir() and d.name not in keep:
        shutil.rmtree(d)
for pg in pages:
    pg.write()
meta = {"$schema": PAGES_SCHEMA, "pageOrder": [pg.pid for pg in pages], "activePageName": pages[0].pid}
(PAGES / "pages.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
print("pages:", [(pg.name, len(pg.visuals)) for pg in pages])
print({k: (round(v, 3) if isinstance(v, float) else v) for k, v in F.items()})
