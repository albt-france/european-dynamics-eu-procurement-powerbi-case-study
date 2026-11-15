"""Write the Power BI semantic model (TMDL) of powerbi/EuroDynProcurement.SemanticModel.

Same method as the earlier case studies (TMDL + PBIR, generated, versioned as text), extended with:
  * partitions read from powerquery/*.pq (single source of truth for the M code);
  * a star schema over SQL Server views, plus a second source (FTS) shaped in Power Query;
  * ~30 measures in display folders, each with a description (/// lines);
  * a calculation group (time variants) and a field parameter (switchable axis);
  * row-level security: role "Agency" (dynamic, USERPRINCIPALNAME) and role "Ministry (all agencies)".
Usage:  python src/build_tmdl.py     (close Power BI Desktop first: the model folder is rewritten)
"""
import json
import shutil
import uuid
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SM = ROOT / "powerbi" / "EuroDynProcurement.SemanticModel"
DEF = SM / "definition"
PQ = ROOT / "powerquery"
DATA_FOLDER = "C:\\case-study-eurodyn\\data\\processed\\"


def tag(*parts):
    """Stable lineage tag, so Power BI sees the same object on every rebuild."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "eurodyn-procurement/" + "/".join(parts)))


def q(name):
    return name if name.replace("_", "").isalnum() else "'" + name.replace("'", "''") + "'"


T = {"int": "int64", "text": "string", "bool": "boolean", "num": "double", "dec": "decimal", "date": "dateTime"}
EUR, EURM, INT, PCT, PCT1, DEC1 = "€#,0", "€#,0.0,,M", "#,0", "0%", "0.0%", "#,0.0"

# (table, pq file, [(column, type, format, hidden, sortBy, extra props)], description)
def c(name, kind, fmt=None, hidden=False, sort=None, **kw):
    return {"name": name, "kind": kind, "fmt": fmt, "hidden": hidden, "sort": sort, **kw}


TABLES = [
    ("FactAward", "One row per published award (notice x lot x winning tender). PUBLIC DATA, TED.", [
        c("AwardKey", "int", hidden=True), c("DateKey", "int", hidden=True), c("BuyerKey", "int", hidden=True),
        c("CountryKey", "int", hidden=True), c("CpvKey", "int", hidden=True), c("ProcedureKey", "int", hidden=True),
        c("EntityKey", "int", hidden=True), c("IsED", "bool"), c("EdRole", "text"), c("PartnerCount", "int", INT),
        c("IsFramework", "bool"), c("NumberOfOffers", "int", INT), c("CountedValueEUR", "dec", EUR, hidden=True),
        c("ValueSplitEUR", "dec", EUR, hidden=True), c("WinnersInLot", "int", INT), c("ValueSource", "text"),
        c("SourceSystem", "text"), c("NoticeId", "text"), c("WinnerLabel", "text"), c("Title", "text"),
        c("TedNoticeUrl", "text", category="WebUrl")]),
    ("DimDate", "Calendar 2016-2026 (marked as date table).", [
        c("DateKey", "int", hidden=True), c("Date", "date", "yyyy-mm-dd", key=True), c("Year", "int", "0"),
        c("Quarter", "int", "0"), c("MonthNo", "int", "0", hidden=True), c("MonthName", "text", sort="MonthNo"),
        c("YearMonth", "text"), c("TedFormat", "text")]),
    ("DimBuyer", "Contracting authorities (normalised names).", [
        c("BuyerKey", "int", hidden=True), c("BuyerName", "text"), c("BuyerType", "text"), c("BuyerGroup", "text"),
        c("BuyerSegment", "text")]),
    ("DimCountry", "Country of the buyer.", [
        c("CountryKey", "int", hidden=True), c("ISO2", "text"), c("ISO3", "text"),
        c("CountryName", "text", category="Country"), c("CountryGroup", "text")]),
    ("DimCPV", "Common Procurement Vocabulary, hierarchy Division > Group > Class > Code.", [
        c("CpvKey", "int", hidden=True), c("CpvCode", "text"), c("CpvLabel", "text"), c("Division", "text"),
        c("Group", "text"), c("Class", "text"), c("CpvCodeLabel", "text"), c("IsITServices", "bool")]),
    ("DimProcedure", "Procurement procedure (legacy TED and eForms codes mapped to one list).", [
        c("ProcedureKey", "int", hidden=True), c("ProcedureLabel", "text", sort="SortOrder"),
        c("ProcedureFamily", "text"), c("SortOrder", "int", "0", hidden=True)]),
    ("DimEntity", "European Dynamics entities after name resolution (0 = other supplier).", [
        c("EntityKey", "int", hidden=True), c("EntityCode", "text"), c("EntityName", "text"), c("EntityKind", "text"),
        c("IsED", "bool")]),
    ("EntityNameMap", "Audit of name resolution: raw spelling -> entity (documentation page).", [
        c("RawName", "text"), c("EntityName", "text"), c("MatchedPattern", "text"), c("SourceSystem", "text"),
        c("Occurrences", "int", INT)]),
    ("FactFts", "Financial Transparency System, European Dynamics rows: legal commitments by year. PUBLIC DATA.", [
        c("Year", "int", "0", hidden=True), c("DateKey", "int", hidden=True), c("EntityCode", "text", hidden=True),
        c("Department", "text", hidden=True), c("Programme", "text", hidden=True), c("ContractType", "text"),
        c("ExpenseType", "text"), c("IsConsortium", "bool"), c("ContractedEUR", "num", EUR, hidden=True),
        c("EstConsumedEUR", "num", EUR, hidden=True)]),
    ("DimDepartment", "Commission departments (FTS).", [
        c("Department", "text"), c("DepartmentCode", "text"), c("DepartmentName", "text")]),
    ("DimProgramme", "EU budget programmes (FTS).", [c("Programme", "text"), c("ProgrammeFamily", "text")]),
    ("FactServiceRequest", "SIMULATED citizen requests of a fictional ministry (RLS demo).", [
        c("RequestId", "text"), c("DateKey", "int", hidden=True), c("AgencyKey", "int", hidden=True),
        c("ServiceName", "text"), c("Channel", "text"), c("Priority", "text"), c("SlaTargetHours", "int", INT),
        c("ResolutionHours", "dec", DEC1, hidden=True), c("IsClosed", "bool"), c("IsSlaMet", "bool"),
        c("Satisfaction", "int", "0", hidden=True)]),
    ("DimAgency", "SIMULATED agencies of the fictional ministry. RLS filters this table.", [
        c("AgencyKey", "int", hidden=True), c("AgencyCode", "text"), c("AgencyName", "text"), c("Ministry", "text")]),
    ("SecUserAgency", "SIMULATED RLS mapping: user principal name -> agency (fictional .example accounts).", [
        c("UserPrincipalName", "text"), c("AgencyCode", "text")]),
    ("QualityChecks", "Results of sql/06_quality_checks.sql.", [
        c("CheckId", "text"), c("CheckName", "text"), c("Actual", "num", "#,0.##"), c("Expected", "text"),
        c("Status", "text"), c("Note", "text")]),
]
HIDDEN_TABLES = {"SecUserAgency", "EntityNameMap", "QualityChecks"}

RELATIONSHIPS = [
    ("FactAward", "DateKey", "DimDate", "DateKey"), ("FactAward", "BuyerKey", "DimBuyer", "BuyerKey"),
    ("FactAward", "CountryKey", "DimCountry", "CountryKey"), ("FactAward", "CpvKey", "DimCPV", "CpvKey"),
    ("FactAward", "ProcedureKey", "DimProcedure", "ProcedureKey"), ("FactAward", "EntityKey", "DimEntity", "EntityKey"),
    ("FactFts", "DateKey", "DimDate", "DateKey"), ("FactFts", "EntityCode", "DimEntity", "EntityCode"),
    ("FactFts", "Department", "DimDepartment", "Department"), ("FactFts", "Programme", "DimProgramme", "Programme"),
    ("FactServiceRequest", "DateKey", "DimDate", "DateKey"), ("FactServiceRequest", "AgencyKey", "DimAgency", "AgencyKey"),
]

ED = "FactAward[IsED] = TRUE ()"
IT = "DimCPV[IsITServices] = TRUE ()"
# (name, DAX, format, folder, description)
MEASURES = [
    # ---- awards
    ("ED Awards", f"CALCULATE ( COUNTROWS ( FactAward ), {ED} )", INT, "1 Awards",
     "Number of award rows (notice x lot x winning tender) won by a European Dynamics entity, alone or in a group."),
    ("All Awards", "COUNTROWS ( FactAward )", INT, "1 Awards",
     "All award rows in the model: European Dynamics plus the CPV 72 market context of the same buyers and EU institutions."),
    ("ED Award Value", f"CALCULATE ( SUM ( FactAward[ValueSplitEUR] ), {ED} )", EURM, "1 Awards",
     "Value of the lots won by European Dynamics, split equally between the winning tenders of a lot (a framework with 5 "
     "winners counts 1/5 of its value). Framework values are ceilings, not spending."),
    ("All Award Value", "SUM ( FactAward[ValueSplitEUR] )", EURM, "1 Awards",
     "Value of all lots in the model, each lot counted once (equal split summed over its winners)."),
    ("ED Ceiling Value", f"CALCULATE ( SUM ( FactAward[CountedValueEUR] ), {ED} )", EURM, "1 Awards",
     "Full published value of lots where European Dynamics is among the winners, counted once per lot (no split). "
     "Upper bound; shown for transparency only."),
    ("ED Median Award Value", f"CALCULATE ( MEDIAN ( FactAward[ValueSplitEUR] ), {ED} )", EUR, "1 Awards",
     "Median equal-split value of a European Dynamics award: robust to the very large framework ceilings."),
    ("ED Buyers", f"CALCULATE ( DISTINCTCOUNT ( FactAward[BuyerKey] ), {ED} )", INT, "1 Awards",
     "Distinct contracting authorities that awarded at least one lot to European Dynamics."),
    ("ED Repeat Buyers", "COUNTROWS ( FILTER ( VALUES ( DimBuyer[BuyerKey] ), [ED Awards] >= 2 ) )", INT, "1 Awards",
     "Buyers with two or more European Dynamics awards in the current filter context (buyer loyalty)."),
    ("ED Repeat Buyer Rate", "DIVIDE ( [ED Repeat Buyers], [ED Buyers] )", PCT, "1 Awards",
     "Share of European Dynamics buyers that awarded it at least twice."),
    ("ED Countries", f"CALCULATE ( DISTINCTCOUNT ( FactAward[CountryKey] ), {ED} )", INT, "1 Awards",
     "Distinct buyer countries (location of the contracting authority, so EU agencies count in their host country)."),
    ("ED Share from EU Institutions",
     f'DIVIDE ( CALCULATE ( [ED Awards], DimBuyer[BuyerSegment] = "EU institutions and agencies" ), [ED Awards] )',
     PCT, "1 Awards", "Share of European Dynamics awards whose buyer is an EU institution, agency or body."),
    ("ED Consortium Share", 'DIVIDE ( CALCULATE ( [ED Awards], FactAward[EdRole] = "Consortium with partners" ), [ED Awards] )',
     PCT, "1 Awards", "Share of European Dynamics awards won together with companies outside the group."),
    # ---- market position and competition
    ("ED Share of CPV 72 Value", f"DIVIDE ( CALCULATE ( [ED Award Value], {IT} ), CALCULATE ( [All Award Value], {IT} ) )",
     PCT1, "2 Market and competition",
     "European Dynamics' equal-split value / value of all CPV 72 (IT services) lots of the same buyers and of EU institutions."),
    ("ED Share of CPV 72 Awards", f"DIVIDE ( CALCULATE ( [ED Awards], {IT} ), CALCULATE ( [All Awards], {IT} ) )",
     PCT1, "2 Market and competition", "Same share, counted in award rows instead of value."),
    ("ED Avg Offers", f"CALCULATE ( AVERAGE ( FactAward[NumberOfOffers] ), {ED} )", DEC1, "2 Market and competition",
     "Average number of offers received on lots won by European Dynamics (where the notice states it)."),
    ("Market Avg Offers", "CALCULATE ( AVERAGE ( FactAward[NumberOfOffers] ), FactAward[IsED] = FALSE () )", DEC1,
     "2 Market and competition", "Average number of offers on the other lots of the model (comparison base)."),
    ("ED Single-Offer Share",
     f"DIVIDE ( CALCULATE ( COUNTROWS ( FactAward ), {ED}, FactAward[NumberOfOffers] = 1 ), "
     f"CALCULATE ( COUNTROWS ( FactAward ), {ED}, NOT ISBLANK ( FactAward[NumberOfOffers] ) ) )",
     PCT, "2 Market and competition",
     "Share of European Dynamics lots that received one offer. One offer is not an anomaly in itself (e.g. negotiated "
     "procedures, specialised maintenance)."),
    ("Market Single-Offer Share",
     "DIVIDE ( CALCULATE ( COUNTROWS ( FactAward ), FactAward[IsED] = FALSE (), FactAward[NumberOfOffers] = 1 ), "
     "CALCULATE ( COUNTROWS ( FactAward ), FactAward[IsED] = FALSE (), NOT ISBLANK ( FactAward[NumberOfOffers] ) ) )",
     PCT, "2 Market and competition", "Same share for the other lots of the model."),
    ("ED Framework Share", f"DIVIDE ( CALCULATE ( [ED Awards], FactAward[IsFramework] = TRUE () ), [ED Awards] )", PCT,
     "2 Market and competition", "Share of European Dynamics awards that are framework agreements."),
    # ---- time intelligence (explicit versions; the calculation group generalises them)
    ("ED Awards YTD", "TOTALYTD ( [ED Awards], DimDate[Date] )", INT, "3 Time intelligence",
     "Year-to-date European Dynamics awards (calendar year)."),
    ("ED Awards PY", "CALCULATE ( [ED Awards], SAMEPERIODLASTYEAR ( DimDate[Date] ) )", INT, "3 Time intelligence",
     "European Dynamics awards in the same period of the previous year."),
    ("ED Awards YoY %", "VAR cur = [ED Awards] VAR py = [ED Awards PY] RETURN IF ( NOT ISBLANK ( py ), DIVIDE ( cur - py, py ) )",
     "+0%;-0%;0%", "3 Time intelligence", "Change versus previous year. 2026 is a partial year (data to mid-November)."),
    ("ED Awards 3Y Moving Avg",
     "VAR lastDate = MAX ( DimDate[Date] ) "
     "RETURN DIVIDE ( CALCULATE ( [ED Awards], DATESINPERIOD ( DimDate[Date], lastDate, -3, YEAR ) ), 3 )",
     DEC1, "3 Time intelligence", "Average yearly awards over the last three years ending at the current date context."),
    # ---- FTS
    ("FTS Contracted", "SUM ( FactFts[ContractedEUR] )", EURM, "4 EU budget (FTS)",
     "European Commission legal commitments to European Dynamics entities, by year of commitment (FTS)."),
    ("FTS Est. Consumed", "SUM ( FactFts[EstConsumedEUR] )", EURM, "4 EU budget (FTS)",
     "Estimated consumed amount of those commitments (payments made until publication, as reported by FTS)."),
    ("FTS Consumption Rate", "DIVIDE ( [FTS Est. Consumed], [FTS Contracted] )",
     PCT, "4 EU budget (FTS)", "Estimated consumed / contracted."),
    ("FTS Top Department Share",
     "DIVIDE ( MAXX ( VALUES ( DimDepartment[Department] ), [FTS Contracted] ), [FTS Contracted] )", PCT,
     "4 EU budget (FTS)", "Share of the largest Commission department in the contracted amount (concentration)."),
    ("FTS Departments", "CALCULATE ( DISTINCTCOUNT ( FactFts[Department] ), FactFts[ContractedEUR] > 0 )", INT,
     "4 EU budget (FTS)", "Commission departments with a positive commitment."),
    # ---- SIMULATED service desk
    ("Requests", "COUNTROWS ( FactServiceRequest )", INT, "5 Service desk (SIMULATED)", "SIMULATED citizen requests."),
    ("SLA Met %",
     "DIVIDE ( CALCULATE ( COUNTROWS ( FactServiceRequest ), FactServiceRequest[IsSlaMet] = TRUE () ), "
     "CALCULATE ( COUNTROWS ( FactServiceRequest ), FactServiceRequest[IsClosed] = TRUE () ) )",
     PCT1, "5 Service desk (SIMULATED)", "Closed requests resolved within their SLA target (24 h high, 72 h normal, 120 h low)."),
    ("SLA Gap vs 90% Target", "[SLA Met %] - 0.9", "+0.0%;-0.0%;0.0%", "5 Service desk (SIMULATED)",
     "Distance to the 90% SLA target set by the fictional ministry."),
    ("Median Resolution (h)", "MEDIAN ( FactServiceRequest[ResolutionHours] )", DEC1, "5 Service desk (SIMULATED)",
     "Median hours from opening to closing (closed requests)."),
    ("P90 Resolution (h)", "PERCENTILE.INC ( FactServiceRequest[ResolutionHours], 0.9 )", DEC1,
     "5 Service desk (SIMULATED)", "90th percentile of resolution time: the slow tail citizens notice."),
    ("Open Backlog", "CALCULATE ( COUNTROWS ( FactServiceRequest ), FactServiceRequest[IsClosed] = FALSE () )", INT,
     "5 Service desk (SIMULATED)", "Requests still open at the end of the simulated period."),
    ("Avg Satisfaction", "AVERAGE ( FactServiceRequest[Satisfaction] )", "0.00", "5 Service desk (SIMULATED)",
     "Average satisfaction score (1-5) of closed requests."),
    ("Visible Agencies Label",
     'VAR n = DISTINCTCOUNT ( DimAgency[AgencyCode] ) RETURN IF ( n = 1, "Agency view: " & SELECTEDVALUE ( DimAgency[AgencyName] ), '
     '"Ministry view: " & n & " agencies" )',
     None, "5 Service desk (SIMULATED)", "Dynamic label: shows which agencies the current user may see (RLS check)."),
]

CALC_ITEMS = [
    ("Selected period", "SELECTEDMEASURE ()", None),
    ("Previous year", "CALCULATE ( SELECTEDMEASURE (), SAMEPERIODLASTYEAR ( DimDate[Date] ) )", None),
    ("YoY change", "VAR cur = SELECTEDMEASURE () "
                   "VAR py = CALCULATE ( SELECTEDMEASURE (), SAMEPERIODLASTYEAR ( DimDate[Date] ) ) "
                   "RETURN IF ( NOT ISBLANK ( py ), cur - py )", None),
    ("YoY %", "VAR cur = SELECTEDMEASURE () "
              "VAR py = CALCULATE ( SELECTEDMEASURE (), SAMEPERIODLASTYEAR ( DimDate[Date] ) ) "
              "RETURN IF ( NOT ISBLANK ( py ), DIVIDE ( cur - py, py ) )", '"+0%;-0%;0%"'),
    ("Year to date", "CALCULATE ( SELECTEDMEASURE (), DATESYTD ( DimDate[Date] ) )", None),
    ("3-year total", "CALCULATE ( SELECTEDMEASURE (), DATESINPERIOD ( DimDate[Date], MAX ( DimDate[Date] ), -3, YEAR ) )", None),
]

AXIS = [("Buyer country", "DimCountry", "CountryName"), ("Buyer segment", "DimBuyer", "BuyerSegment"),
        ("CPV division", "DimCPV", "Division"), ("Procedure", "DimProcedure", "ProcedureLabel"),
        ("European Dynamics entity", "DimEntity", "EntityName")]


# ---------------------------------------------------------------- writers
def desc(text, indent="\t"):
    return [f"{indent}/// {text}"]


def column_block(table, col):
    lines = [f"\tcolumn {q(col['name'])}", f"\t\tdataType: {T[col['kind']]}"]
    if col.get("key"):
        lines.append("\t\tisKey")
    if col["hidden"]:
        lines.append("\t\tisHidden")
    if col["fmt"]:
        lines.append(f"\t\tformatString: {col['fmt']}")
    if col.get("category"):
        lines.append(f"\t\tdataCategory: {col['category']}")
    summarize = "none"
    lines += [f"\t\tlineageTag: {tag(table, col['name'])}", f"\t\tsummarizeBy: {summarize}",
              f"\t\tsourceColumn: {col['name']}"]
    if col["sort"]:
        lines.append(f"\t\tsortByColumn: {q(col['sort'])}")
    if col["kind"] == "date":
        lines += ["", "\t\tannotation UnderlyingDateTimeDataType = Date"]
    return "\n".join(lines) + "\n"


def m_block(text, indent="\t\t\t\t"):
    return "\n".join(indent + l if l.strip() else "" for l in text.rstrip().splitlines())


def write_table(name, description, cols):
    out = desc(description, "") + [f"table {q(name)}", f"\tlineageTag: {tag(name)}"]
    if name in HIDDEN_TABLES:
        out.append("\tisHidden")
    if name == "DimDate":
        out.append("\tdataCategory: Time")
    out.append("")
    for col in cols:
        out.append(column_block(name, col))
    if name == "DimCPV":
        out += ["\thierarchy 'CPV hierarchy'", f"\t\tlineageTag: {tag(name, 'h')}", ""]
        for lvl in ("Division", "Group", "Class", "CpvCodeLabel"):
            out += [f"\t\tlevel {lvl}", f"\t\t\tlineageTag: {tag(name, 'h', lvl)}", f"\t\t\tcolumn: {lvl}", ""]
    m = (PQ / f"{name}.pq").read_text(encoding="utf-8")
    out += [f"\tpartition {q(name)} = m", "\t\tmode: import", "\t\tsource =", m_block(m), ""]
    return "\n".join(out) + "\n"


def write_measures():
    out = ["/// Home table of all measures (display folders = report sections).", "table _Measures",
           f"\tlineageTag: {tag('_Measures')}", ""]
    for name, dax, fmt, folder, d in MEASURES:
        out += desc(d) + [f"\tmeasure {q(name)} = {dax}"]
        if fmt:
            out.append(f"\t\tformatString: {fmt}")
        out += [f"\t\tdisplayFolder: {folder}", f"\t\tlineageTag: {tag('_Measures', name)}", ""]
    out += ["\tcolumn _", "\t\tdataType: string", "\t\tisHidden", f"\t\tlineageTag: {tag('_Measures', '_')}",
            "\t\tsummarizeBy: none", "\t\tsourceColumn: _", "",
            "\tpartition _Measures = m", "\t\tmode: import", "\t\tsource = #table(type table [_ = text], {})", ""]
    return "\n".join(out) + "\n"


def write_calc_group():
    out = ["/// Calculation group: applies the same time variant to any measure (one definition instead of N x 6 measures).",
           "table 'Time Calc'", f"\tlineageTag: {tag('TimeCalc')}", "", "\tcalculationGroup", "\t\tprecedence: 10", ""]
    for i, (name, dax, fmt) in enumerate(CALC_ITEMS):
        out += [f"\t\tcalculationItem {q(name)} = {dax}"]
        out += [f"\t\t\tordinal: {i}"]
        if fmt:
            out += [f"\t\t\tformatStringDefinition = {fmt}"]
        out.append("")
    out += ["\tcolumn Period", "\t\tdataType: string", f"\t\tlineageTag: {tag('TimeCalc', 'Period')}",
            "\t\tsummarizeBy: none", "\t\tsourceColumn: Name", "\t\tsortByColumn: Ordinal", "",
            "\tcolumn Ordinal", "\t\tdataType: int64", "\t\tisHidden", f"\t\tlineageTag: {tag('TimeCalc', 'Ordinal')}",
            "\t\tsummarizeBy: none", "\t\tsourceColumn: Ordinal", "",
            "\tpartition 'Time Calc' = calculationGroup", "\t\tmode: import", ""]
    return "\n".join(out) + "\n"


def write_field_parameter():
    rows = ",\n".join(f'\t\t\t\t\t("{lbl}", NAMEOF ( \'{t}\'[{col}] ), {i})' for i, (lbl, t, col) in enumerate(AXIS))
    return "\n".join([
        "/// Field parameter: lets the reader switch the axis of the comparison charts.",
        "table Axis", f"\tlineageTag: {tag('Axis')}", "",
        "\tcolumn Axis", "\t\tdataType: string", f"\t\tlineageTag: {tag('Axis', 'Axis')}", "\t\tsummarizeBy: none",
        "\t\tsourceColumn: [Value1]", "\t\tsortByColumn: 'Axis Order'", "", "\t\trelatedColumnDetails",
        "\t\t\tgroupByColumn: 'Axis Fields'", "",
        "\tcolumn 'Axis Fields'", "\t\tdataType: string", "\t\tisHidden", f"\t\tlineageTag: {tag('Axis', 'Fields')}",
        "\t\tsummarizeBy: none", "\t\tsourceColumn: [Value2]", "\t\tsortByColumn: 'Axis Order'", "",
        "\t\textendedProperty ParameterMetadata =", "\t\t\t\t{", '\t\t\t\t  "version": 3,', '\t\t\t\t  "kind": 2', "\t\t\t\t}", "",
        "\tcolumn 'Axis Order'", "\t\tdataType: int64", "\t\tisHidden", "\t\tformatString: 0",
        f"\t\tlineageTag: {tag('Axis', 'Order')}", "\t\tsummarizeBy: none", "\t\tsourceColumn: [Value3]", "",
        "\tpartition Axis = calculated", "\t\tmode: import", "\t\tsource =", "\t\t\t\t{", rows, "\t\t\t\t}", "",
        "\tannotation PBI_Id = " + tag("Axis", "id").replace("-", ""), ""]) + "\n"


def write_ml_tables():
    fi = pd.read_csv(ROOT / "data" / "processed" / "ml_feature_importance.csv")
    mt = json.loads((ROOT / "data" / "processed" / "ml_metrics.json").read_text())
    rows = ", ".join("{" + f'"{r.feature}", {r.importance:.4f}, {int(r["rank"])}' + "}" for _, r in fi.iterrows())
    t1 = "\n".join([
        "/// Permutation importance (drop in ROC AUC) of the single-offer model, src/ml_single_offer.py. PUBLIC DATA.",
        "table 'ML Feature Importance'", f"\tlineageTag: {tag('MLFI')}", "",
        "\tcolumn Feature", "\t\tdataType: string", f"\t\tlineageTag: {tag('MLFI', 'f')}", "\t\tsummarizeBy: none",
        "\t\tsourceColumn: Feature", "\t\tsortByColumn: Rank", "",
        "\tcolumn Importance", "\t\tdataType: double", "\t\tformatString: 0.000", f"\t\tlineageTag: {tag('MLFI', 'i')}",
        "\t\tsummarizeBy: sum", "\t\tsourceColumn: Importance", "",
        "\tcolumn Rank", "\t\tdataType: int64", "\t\tisHidden", "\t\tformatString: 0", f"\t\tlineageTag: {tag('MLFI', 'r')}",
        "\t\tsummarizeBy: none", "\t\tsourceColumn: Rank", "",
        "\tpartition 'ML Feature Importance' = m", "\t\tmode: import",
        f"\t\tsource = #table(type table [Feature = text, Importance = number, Rank = Int64.Type], {{{rows}}})", ""])
    best = mt["models"][mt["best_model"]]
    lr = mt["models"]["Logistic regression"]
    metr = [("Rows (IT lots with offers stated)", mt["rows"], "0"), ("Single-offer rate", mt["single_offer_rate"], "pct"),
            (f"ROC AUC, {mt['best_model'].lower()} (5-fold CV)", best["roc_auc"], "dec"),
            ("ROC AUC, logistic regression (5-fold CV)", lr["roc_auc"], "dec"),
            ("Average precision, best model", best["avg_precision"], "dec")]
    mrows = ", ".join("{" + f'"{a}", {b}, "{"{:.0%}".format(b) if k == "pct" else ("{:.2f}".format(b) if k == "dec" else f"{b:,}")}"' + "}"
                      for a, b, k in metr)
    t2 = "\n".join([
        "/// Cross-validated metrics of the single-offer model.", "table 'ML Metrics'", f"\tlineageTag: {tag('MLM')}", "",
        "\tcolumn Metric", "\t\tdataType: string", f"\t\tlineageTag: {tag('MLM', 'm')}", "\t\tsummarizeBy: none",
        "\t\tsourceColumn: Metric", "",
        "\tcolumn Value", "\t\tdataType: double", "\t\tisHidden", f"\t\tlineageTag: {tag('MLM', 'v')}", "\t\tsummarizeBy: none",
        "\t\tsourceColumn: Value", "",
        "\tcolumn Display", "\t\tdataType: string", f"\t\tlineageTag: {tag('MLM', 'd')}", "\t\tsummarizeBy: none",
        "\t\tsourceColumn: Display", "",
        "\tpartition 'ML Metrics' = m", "\t\tmode: import",
        f"\t\tsource = #table(type table [Metric = text, Value = number, Display = text], {{{mrows}}})", ""])
    return t1 + "\n", t2 + "\n"


ROLES = {
    "Agency": ("Dynamic RLS: a signed-in user sees only the agencies mapped to their account in SecUserAgency.",
               [("DimAgency", "[AgencyCode] IN CALCULATETABLE ( VALUES ( SecUserAgency[AgencyCode] ), "
                              "SecUserAgency[UserPrincipalName] = USERPRINCIPALNAME () )"),
                ("SecUserAgency", "[UserPrincipalName] = USERPRINCIPALNAME ()")]),
    "Ministry (all agencies)": ("Ministry management: every agency, read only.", []),
}


def main():
    if DEF.exists():
        shutil.rmtree(DEF)
    (DEF / "tables").mkdir(parents=True)
    (DEF / "roles").mkdir()
    (SM / "definition.pbism").write_text(json.dumps({"version": "4.2", "settings": {}}, indent=2), encoding="utf-8")
    names = []
    for name, d, cols in TABLES:
        (DEF / "tables" / f"{name}.tmdl").write_text(write_table(name, d, cols), encoding="utf-8")
        names.append(name)
    t1, t2 = write_ml_tables()
    (DEF / "tables" / "ML Feature Importance.tmdl").write_text(t1, encoding="utf-8")
    (DEF / "tables" / "ML Metrics.tmdl").write_text(t2, encoding="utf-8")
    (DEF / "tables" / "Time Calc.tmdl").write_text(write_calc_group(), encoding="utf-8")
    (DEF / "tables" / "Axis.tmdl").write_text(write_field_parameter(), encoding="utf-8")
    (DEF / "tables" / "_Measures.tmdl").write_text(write_measures(), encoding="utf-8")
    names += ["ML Feature Importance", "ML Metrics", "Time Calc", "Axis", "_Measures"]

    for role, (d, perms) in ROLES.items():
        lines = [f"/// {d}", f"role {q(role)}", "\tmodelPermission: read", ""]
        for t, expr in perms:
            lines += [f"\ttablePermission {q(t)} = {expr}", ""]
        lines.append(f"\tannotation PBI_Id = {tag('role', role).replace('-', '')}")
        (DEF / "roles" / f"{role}.tmdl").write_text("\n".join(lines) + "\n", encoding="utf-8")

    (DEF / "database.tmdl").write_text("database\n\tcompatibilityLevel: 1600\n\n", encoding="utf-8")
    model = ["model Model", "\tculture: en-US", "\tdefaultPowerBIDataSourceVersion: powerBI_V3",
             "\tdiscourageImplicitMeasures", "\tsourceQueryCulture: en-US", "\tdataAccessOptions",
             "\t\tlegacyRedirects", "\t\treturnErrorValuesAsNull", "",
             "annotation __PBI_TimeIntelligenceEnabled = 0", "",
             'annotation PBI_QueryOrder = ["ServerName","DatabaseName","DataFolder","FtsStaging"]', "",
             'annotation PBI_ProTooling = ["TMDLView_Desktop","DevMode","CalcGroup"]', ""]
    model += [f"ref table {q(n)}" for n in names] + [""] + [f"ref role {q(r)}" for r in ROLES] + [""]
    (DEF / "model.tmdl").write_text("\n".join(model), encoding="utf-8")

    def param(name, value, d):
        return (f'/// {d}\nexpression {name} = "{value}" meta [IsParameterQuery=true, Type="Text", IsParameterQueryRequired=true]\n'
                f"\tlineageTag: {tag(name)}\n\n\tannotation PBI_ResultType = Text\n\n")
    fts = (PQ / "FtsStaging.pq").read_text(encoding="utf-8")
    expr = (param("ServerName", "(localdb)\\\\MSSQLLocalDB".replace("\\\\", "\\"), "SQL Server instance (neutral default: LocalDB).")
            + param("DatabaseName", "EuroDynDW", "Warehouse database built by src/load_sql.py.")
            + param("DataFolder", DATA_FOLDER, "Folder of the processed extracts (FTS CSV fallback, QA results).")
            + "/// Staging query for the FTS rows (not loaded; referenced by FactFts, DimDepartment, DimProgramme).\n"
            + "expression FtsStaging =\n" + m_block(fts, "\t\t") + "\n"
            + f"\tlineageTag: {tag('FtsStaging')}\n\n\tannotation PBI_NavigationStepName = Navigation\n\n"
            + "\tannotation PBI_ResultType = Table\n\n")
    (DEF / "expressions.tmdl").write_text(expr, encoding="utf-8")

    rels = []
    for ft, fc, tt, tc in RELATIONSHIPS:
        rels += [f"relationship {tag('rel', ft, fc, tt)}", f"\tfromColumn: {q(ft)}.{q(fc)}", f"\ttoColumn: {q(tt)}.{q(tc)}", ""]
    (DEF / "relationships.tmdl").write_text("\n".join(rels), encoding="utf-8")
    print(f"semantic model: {len(names)} tables, {len(MEASURES)} measures, {len(CALC_ITEMS)} calculation items, "
          f"{len(RELATIONSHIPS)} relationships, {len(ROLES)} roles")


if __name__ == "__main__":
    main()
