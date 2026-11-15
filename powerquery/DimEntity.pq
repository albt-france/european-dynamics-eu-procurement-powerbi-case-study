// DimEntity: PUBLIC DATA (TED), star schema dwh
// Source: SQL Server view pbi.vDimEntity (sql/05_views_powerbi.sql). Every step folds to SQL Server:
// right-click the last step > View Native Query shows a single SELECT. The same M runs unchanged in a
// Power BI dataflow (Power Query Online, through the on-premises data gateway): see docs/DATAFLOWS.md.
let
    Source = Sql.Database(ServerName, DatabaseName),
    View = Source{[Schema = "pbi", Item = "vDimEntity"]}[Data],
    Selected = Table.SelectColumns(View, {"EntityKey", "EntityCode", "EntityName", "EntityKind", "IsED"})
in
    Selected
