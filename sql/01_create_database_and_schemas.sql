/* =====================================================================================================
   01  Database and schemas
   Target: SQL Server 2016+ (tested on SQL Server 2016 LocalDB 13.0, also valid on SQL Server Express).
   Layers
     stg  raw landing zone: one table per extract, every column NVARCHAR, loaded as-is by src/load_sql.py
     ref  hand-maintained reference data (entity aliases, code lists)
     dwh  star schema (typed, keyed, indexed) - the only layer Power BI reads, through views in schema pbi
     pbi  views exposed to Power BI (stable contract: rename / reshape here, never in the report)
     sim  SIMULATED e-Government service desk (fictional ministry), kept apart from public data
     qa   data-quality check results
   ===================================================================================================== */
IF DB_ID(N'EuroDynDW') IS NULL
    CREATE DATABASE EuroDynDW;
GO
USE EuroDynDW;
GO
IF SCHEMA_ID(N'stg') IS NULL EXEC (N'CREATE SCHEMA stg');
IF SCHEMA_ID(N'ref') IS NULL EXEC (N'CREATE SCHEMA ref');
IF SCHEMA_ID(N'dwh') IS NULL EXEC (N'CREATE SCHEMA dwh');
IF SCHEMA_ID(N'pbi') IS NULL EXEC (N'CREATE SCHEMA pbi');
IF SCHEMA_ID(N'sim') IS NULL EXEC (N'CREATE SCHEMA sim');
IF SCHEMA_ID(N'qa')  IS NULL EXEC (N'CREATE SCHEMA qa');
GO
