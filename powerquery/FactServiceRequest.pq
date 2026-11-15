// FactServiceRequest: SIMULATED data (fictional ministry), schema sim
// Source: SQL Server view pbi.vFactServiceRequest (sql/05_views_powerbi.sql). Every step folds to SQL Server:
// right-click the last step > View Native Query shows a single SELECT. The same M runs unchanged in a
// Power BI dataflow (Power Query Online, through the on-premises data gateway): see docs/DATAFLOWS.md.
let
    Source = Sql.Database(ServerName, DatabaseName),
    View = Source{[Schema = "pbi", Item = "vFactServiceRequest"]}[Data],
    Selected = Table.SelectColumns(View, {"RequestId", "DateKey", "AgencyKey", "ServiceName", "Channel", "Priority", "SlaTargetHours", "ResolutionHours", "IsClosed", "IsSlaMet", "Satisfaction"})
in
    Selected
