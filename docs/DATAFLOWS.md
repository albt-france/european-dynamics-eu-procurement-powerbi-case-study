# Dataflows: reusing the Power Query layer in the Power BI Service

The M code in `powerquery/*.pq` is written so that it can move, unchanged, from Power BI Desktop to a **Power BI
dataflow (Gen1) or a Fabric Dataflow Gen2**, and be shared by several semantic models.

## Why a dataflow here

* The same cleaned tables (dimensions especially: `DimBuyer`, `DimCPV`, `DimCountry`, `DimDate`) would serve more than
  one report (procurement, finance, a future tender pipeline). A dataflow prepares them **once**, refreshes them **once**,
  and every model connects to the dataflow instead of repeating the logic.
* The SQL Server warehouse is on premises: the dataflow reaches it through the **on-premises data gateway**, so only
  the gateway needs network access to the database, not every report author.

## Design

| Dataflow | Entities | Source | Refresh |
|---|---|---|---|
| `DF_Procurement_Dimensions` | DimDate, DimBuyer, DimCountry, DimCPV, DimProcedure, DimEntity | SQL Server views `pbi.*` via gateway | daily 05:00 |
| `DF_Procurement_Facts` | FactAward | `pbi.vFactAward` via gateway | daily 05:30, **incremental**: store 11 years, refresh the last 2 months (`DateKey` filter folds to SQL) |
| `DF_EU_Budget` | FtsStaging (staging entity, not exposed), FactFts, DimDepartment, DimProgramme | PostgreSQL `fts.fts_ed` via gateway (CSV in this repository) | yearly after the FTS publication + monthly check |

Rules followed in the M code so it ports cleanly:

1. **Parameters, not hard-coded servers**: `ServerName`, `DatabaseName`, `DataFolder` (and `PgServer`, `PgDatabase`
   for PostgreSQL) become dataflow parameters; Dev / Test / Prod differ only by parameter values.
2. **Query folding first**: every SQL Server query is `Sql.Database` -> navigation to a view -> `Table.SelectColumns`
   -> `Table.SelectRows`. All steps fold into one native SELECT (check: *View Native Query*). This is what makes
   incremental refresh possible: the `RangeStart` / `RangeEnd` filter must fold to the source.
3. **Staging vs. computed entities**: `FtsStaging` is a staging query referenced by three tables. In a dataflow it
   becomes a staging entity (load disabled in Gen1 Pro; in Premium / Fabric, a computed entity reuses its stored result
   instead of re-reading the source three times).
4. **Explicit types on every column** (`Table.TransformColumnTypes` with culture `en-US`), so the dataflow schema is
   stable and the model does not re-detect types.
5. **No Desktop-only functions** (no local file pickers, no R / Python steps). The fuzzy merge
   (`Table.FuzzyNestedJoin`) is supported in dataflows.

## How the semantic model consumes it

In the model, each partition becomes `PowerPlatform.Dataflows(null)` -> workspace -> dataflow -> entity. Measures,
relationships, RLS and the calculation group are unchanged: only the partition sources change, which is why the
model keeps one partition expression per table (generated from `powerquery/`).

## Status in this case study

Designed and written so that it ports to a dataflow; **run in Power BI Desktop only** (no Power BI Service tenant was
used). See `SERVICE_DEPLOYMENT.md` for the workspace and gateway set-up.
