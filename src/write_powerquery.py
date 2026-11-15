"""Write the Power Query (M) files of powerquery/ for the SQL Server views.

The M code in powerquery/*.pq is the single source of truth: src/build_tmdl.py inlines each file into the
semantic model (one partition per table), so what is reviewed in git is exactly what Power BI runs.
The FTS queries (FtsStaging, FactFts, DimDepartment, DimProgramme) and QualityChecks are hand-written files.
Usage:  python src/write_powerquery.py
"""
from pathlib import Path

P = Path(__file__).resolve().parents[1] / "powerquery"

SQL_TABLES = {
    "FactAward": ("vFactAward", ["AwardKey", "DateKey", "BuyerKey", "CountryKey", "CpvKey", "ProcedureKey", "EntityKey",
                                 "IsED", "EdRole", "PartnerCount", "IsFramework", "NumberOfOffers", "CountedValueEUR",
                                 "ValueSplitEUR", "WinnersInLot", "ValueSource", "SourceSystem", "NoticeId",
                                 "WinnerLabel", "Title", "TedNoticeUrl"]),
    "DimDate": ("vDimDate", ["DateKey", "Date", "Year", "Quarter", "MonthNo", "MonthName", "YearMonth", "TedFormat"]),
    "DimBuyer": ("vDimBuyer", ["BuyerKey", "BuyerName", "BuyerType", "BuyerGroup", "BuyerSegment"]),
    "DimCountry": ("vDimCountry", ["CountryKey", "ISO2", "ISO3", "CountryName", "CountryGroup"]),
    "DimCPV": ("vDimCPV", ["CpvKey", "CpvCode", "CpvLabel", "Division", "Group", "Class", "CpvCodeLabel", "IsITServices"]),
    "DimProcedure": ("vDimProcedure", ["ProcedureKey", "ProcedureLabel", "ProcedureFamily", "SortOrder"]),
    "DimEntity": ("vDimEntity", ["EntityKey", "EntityCode", "EntityName", "EntityKind", "IsED"]),
    "EntityNameMap": ("vEntityNameMap", ["RawName", "EntityName", "MatchedPattern", "SourceSystem", "Occurrences"]),
    "FactServiceRequest": ("vFactServiceRequest", ["RequestId", "DateKey", "AgencyKey", "ServiceName", "Channel",
                                                   "Priority", "SlaTargetHours", "ResolutionHours", "IsClosed",
                                                   "IsSlaMet", "Satisfaction"]),
    "DimAgency": ("vDimAgency", ["AgencyKey", "AgencyCode", "AgencyName", "Ministry"]),
    "SecUserAgency": ("vSecUserAgency", ["UserPrincipalName", "AgencyCode"]),
}


def main():
    P.mkdir(exist_ok=True)
    for name, (view, cols) in SQL_TABLES.items():
        sim = name in ("FactServiceRequest", "DimAgency", "SecUserAgency")
        note = "SIMULATED data (fictional ministry), schema sim" if sim else "PUBLIC DATA (TED), star schema dwh"
        steps = [f'    Source = Sql.Database(ServerName, DatabaseName),',
                 f'    View = Source{{[Schema = "pbi", Item = "{view}"]}}[Data],',
                 f'    Selected = Table.SelectColumns(View, {{{", ".join(chr(34) + c + chr(34) for c in cols)}}})']
        last = "Selected"
        if name == "FactAward":
            steps[-1] += ","
            steps += ["    // 2016 onwards: folds into the WHERE clause of the native query",
                      "    Recent = Table.SelectRows(Selected, each [DateKey] >= 20160101)"]
            last = "Recent"
        m = "\n".join([
            f"// {name}: {note}",
            f"// Source: SQL Server view pbi.{view} (sql/05_views_powerbi.sql). Every step folds to SQL Server:",
            "// right-click the last step > View Native Query shows a single SELECT. The same M runs unchanged in a",
            "// Power BI dataflow (Power Query Online, through the on-premises data gateway): see docs/DATAFLOWS.md.",
            "let", *steps, "in", f"    {last}", ""])
        (P / f"{name}.pq").write_text(m, encoding="utf-8")
    print(sorted(p.name for p in P.glob("*.pq")))


if __name__ == "__main__":
    main()
