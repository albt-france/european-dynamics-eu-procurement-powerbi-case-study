/* =====================================================================================================
   05  Views for Power BI (schema pbi) - the contract between the warehouse and the semantic model
   Rules: only the columns the report uses (narrow import = smaller model), friendly names, one view per model
   table, simple SELECTs so that Power Query folds every step back to SQL Server (no scalar UDF here).
   CountedValueEUR is pre-computed (value only on the counted row of a notice-lot) so that DAX can use a plain
   SUM instead of a filtered CALCULATE: cheaper and impossible to double count by mistake.
   ===================================================================================================== */
USE EuroDynDW;
GO
DROP VIEW IF EXISTS pbi.vFactAward;
GO
CREATE VIEW pbi.vFactAward AS
SELECT f.AwardKey, f.DateKey, f.BuyerKey, f.CountryKey, f.CpvKey, f.ProcedureKey, f.EntityKey,
       f.IsED, f.EdRole, f.PartnerCount, f.IsFramework, f.NumberOfOffers,
       IIF(f.IsValueCounted = 1, f.ValueEUR, NULL) AS CountedValueEUR,
       f.ValueSplitEUR, f.WinnersInLot,
       f.ValueSource, f.SourceSystem, f.NoticeId, f.LotId, f.WinnerLabel, f.Title,
       N'https://ted.europa.eu/en/notice/-/detail/' + f.NoticeId AS TedNoticeUrl
FROM dwh.FactAward f;
GO
DROP VIEW IF EXISTS pbi.vDimDate;
GO
CREATE VIEW pbi.vDimDate AS
SELECT DateKey, [Date], [Year], Quarter, MonthNo, MonthName, YearMonth, TedFormat FROM dwh.DimDate;
GO
DROP VIEW IF EXISTS pbi.vDimBuyer;
GO
CREATE VIEW pbi.vDimBuyer AS
SELECT BuyerKey, BuyerName, CountryISO3, BuyerType, BuyerGroup,
       IIF(IsEU = 1, N'EU institutions and agencies', N'National and other public buyers') AS BuyerSegment
FROM dwh.DimBuyer;
GO
DROP VIEW IF EXISTS pbi.vDimCountry;
GO
CREATE VIEW pbi.vDimCountry AS
SELECT CountryKey, ISO2, ISO3, CountryName, IIF(IsEUMember = 1, N'EU member state', N'Other country') AS CountryGroup
FROM dwh.DimCountry;
GO
DROP VIEW IF EXISTS pbi.vDimCPV;
GO
CREATE VIEW pbi.vDimCPV AS
SELECT CpvKey, CpvCode, CpvLabel, DivisionCode, DivisionCode + N' ' + DivisionLabel AS Division,
       GroupCode + N' ' + GroupLabel AS [Group], ClassCode + N' ' + ClassLabel AS Class,
       CpvCode + N' ' + CpvLabel AS CpvCodeLabel, IsITServices
FROM dwh.DimCPV;
GO
DROP VIEW IF EXISTS pbi.vDimProcedure;
GO
CREATE VIEW pbi.vDimProcedure AS
SELECT ProcedureKey, ProcedureLabel, ProcedureFamily, SortOrder FROM dwh.DimProcedure;
GO
DROP VIEW IF EXISTS pbi.vDimEntity;
GO
CREATE VIEW pbi.vDimEntity AS
SELECT EntityKey, EntityCode, EntityName, EntityCountry, EntityKind, IsED FROM dwh.DimEntity;
GO
DROP VIEW IF EXISTS pbi.vFactFts;
GO
CREATE VIEW pbi.vFactFts AS
SELECT f.FtsKey, f.[Year], f.DateKey, f.EntityKey, f.DepartmentKey, f.ProgrammeKey, f.ContractType, f.ExpenseType,
       f.IsConsortium, f.ContractedEUR, f.EstConsumedEUR
FROM dwh.FactFts f;
GO
DROP VIEW IF EXISTS pbi.vDimDepartment;
GO
CREATE VIEW pbi.vDimDepartment AS
SELECT DepartmentKey, DepartmentCode, DepartmentName, DepartmentCode + N' - ' + DepartmentName AS Department
FROM dwh.DimDepartment;
GO
DROP VIEW IF EXISTS pbi.vDimProgramme;
GO
CREATE VIEW pbi.vDimProgramme AS SELECT ProgrammeKey, ProgrammeName, ProgrammeFamily FROM dwh.DimProgramme;
GO
DROP VIEW IF EXISTS pbi.vEntityNameMap;
GO
CREATE VIEW pbi.vEntityNameMap AS
SELECT m.RawName, m.NormName, e.EntityName, m.MatchedPattern, m.SourceSystem, m.Occurrences
FROM dwh.EntityNameMap m JOIN dwh.DimEntity e ON e.EntityCode = m.EntityCode;
GO
/* ---------------- SIMULATED service desk ---------------- */
DROP VIEW IF EXISTS pbi.vFactServiceRequest;
GO
CREATE VIEW pbi.vFactServiceRequest AS
SELECT RequestId, DateKey, AgencyKey, ServiceName, Channel, Priority, SlaTargetHours, ResolutionHours,
       IsClosed, IsSlaMet, Satisfaction
FROM sim.FactServiceRequest;
GO
DROP VIEW IF EXISTS pbi.vDimAgency;
GO
CREATE VIEW pbi.vDimAgency AS SELECT AgencyKey, AgencyCode, AgencyName, Ministry FROM sim.DimAgency;
GO
DROP VIEW IF EXISTS pbi.vSecUserAgency;
GO
CREATE VIEW pbi.vSecUserAgency AS SELECT UserPrincipalName, AgencyCode FROM sim.SecUserAgency;
GO
