// FactAward: PUBLIC DATA (TED), star schema dwh
// Source: SQL Server view pbi.vFactAward (sql/05_views_powerbi.sql). Every step folds to SQL Server:
// right-click the last step > View Native Query shows a single SELECT. The same M runs unchanged in a
// Power BI dataflow (Power Query Online, through the on-premises data gateway): see docs/DATAFLOWS.md.
let
    Source = Sql.Database(ServerName, DatabaseName),
    View = Source{[Schema = "pbi", Item = "vFactAward"]}[Data],
    Selected = Table.SelectColumns(View, {"AwardKey", "DateKey", "BuyerKey", "CountryKey", "CpvKey", "ProcedureKey", "EntityKey", "IsED", "EdRole", "PartnerCount", "IsFramework", "NumberOfOffers", "CountedValueEUR", "ValueSplitEUR", "WinnersInLot", "ValueSource", "SourceSystem", "NoticeId", "WinnerLabel", "Title", "TedNoticeUrl"}),
    // 2016 onwards: folds into the WHERE clause of the native query
    Recent = Table.SelectRows(Selected, each [DateKey] >= 20160101)
in
    Recent
