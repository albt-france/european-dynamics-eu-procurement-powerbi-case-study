/* =====================================================================================================
   07  Analysis queries (CTE + window functions) - the questions of the report, answered in SQL
   Run in SSMS / Azure Data Studio against EuroDynDW. Each query is independent.
   ===================================================================================================== */
USE EuroDynDW;
GO

/* Q1  Awards per year, running total and 3-year moving average (window frame) */
WITH y AS (
    SELECT d.[Year], COUNT(*) AS Awards
    FROM dwh.FactAward f JOIN dwh.DimDate d ON d.DateKey = f.DateKey
    WHERE f.IsED = 1
    GROUP BY d.[Year])
SELECT [Year], Awards,
       SUM(Awards) OVER (ORDER BY [Year] ROWS UNBOUNDED PRECEDING)               AS RunningTotal,
       AVG(1.0 * Awards) OVER (ORDER BY [Year] ROWS BETWEEN 2 PRECEDING AND CURRENT ROW) AS MovingAvg3Y,
       Awards - LAG(Awards) OVER (ORDER BY [Year])                               AS ChangeVsPY
FROM y ORDER BY [Year];

/* Q2  Buyer loyalty: first and last award, number of awards, rank within buyer segment */
WITH b AS (
    SELECT f.BuyerKey, COUNT(*) AS Awards, MIN(d.[Date]) AS FirstAward, MAX(d.[Date]) AS LastAward
    FROM dwh.FactAward f JOIN dwh.DimDate d ON d.DateKey = f.DateKey
    WHERE f.IsED = 1 GROUP BY f.BuyerKey)
SELECT TOP (20) db.BuyerName, db.BuyerGroup, b.Awards, b.FirstAward, b.LastAward,
       DATEDIFF(YEAR, b.FirstAward, b.LastAward) AS YearsOfRelationship,
       DENSE_RANK() OVER (PARTITION BY db.BuyerGroup ORDER BY b.Awards DESC) AS RankInGroup
FROM b JOIN dwh.DimBuyer db ON db.BuyerKey = b.BuyerKey
ORDER BY b.Awards DESC;

/* Q3  Share of CPV 72 lots per buyer segment and year (conditional aggregation + share of total) */
WITH s AS (
    SELECT d.[Year], b.BuyerGroup,
           SUM(IIF(f.IsED = 1, 1, 0)) AS EdLots, COUNT(*) AS AllLots,
           SUM(IIF(f.IsED = 1, f.ValueSplitEUR, 0)) AS EdValue, SUM(f.ValueSplitEUR) AS AllValue
    FROM dwh.FactAward f
    JOIN dwh.DimDate d ON d.DateKey = f.DateKey
    JOIN dwh.DimBuyer b ON b.BuyerKey = f.BuyerKey
    JOIN dwh.DimCPV c ON c.CpvKey = f.CpvKey
    WHERE c.IsITServices = 1
    GROUP BY d.[Year], b.BuyerGroup)
SELECT [Year], BuyerGroup, EdLots, AllLots,
       CAST(100.0 * EdLots / NULLIF(AllLots, 0) AS DECIMAL(5,1)) AS EdShareLotsPct,
       CAST(100.0 * EdValue / NULLIF(AllValue, 0) AS DECIMAL(5,1)) AS EdShareValuePct
FROM s WHERE EdLots > 0 ORDER BY [Year], BuyerGroup;

/* Q4  Competition: offers received, ED lots vs other lots of the same buyers, by procedure */
SELECT p.ProcedureFamily,
       SUM(IIF(f.IsED = 1, 1, 0)) AS EdLots,
       AVG(IIF(f.IsED = 1, 1.0 * f.NumberOfOffers, NULL)) AS EdAvgOffers,
       AVG(IIF(f.IsED = 0, 1.0 * f.NumberOfOffers, NULL)) AS OtherAvgOffers,
       AVG(IIF(f.IsED = 1, IIF(f.NumberOfOffers = 1, 1.0, 0.0), NULL)) AS EdSingleOfferShare,
       AVG(IIF(f.IsED = 0, IIF(f.NumberOfOffers = 1, 1.0, 0.0), NULL)) AS OtherSingleOfferShare
FROM dwh.FactAward f JOIN dwh.DimProcedure p ON p.ProcedureKey = f.ProcedureKey
WHERE f.NumberOfOffers IS NOT NULL
GROUP BY p.ProcedureFamily ORDER BY EdLots DESC;

/* Q5  Most frequent other winners at the buyers of European Dynamics (CPV 72), neutral listing */
WITH edBuyers AS (SELECT DISTINCT BuyerKey FROM dwh.FactAward WHERE IsED = 1),
w AS (
    SELECT f.WinnerLabel, COUNT(*) AS Lots, COUNT(DISTINCT f.BuyerKey) AS Buyers
    FROM dwh.FactAward f
    JOIN edBuyers e ON e.BuyerKey = f.BuyerKey
    JOIN dwh.DimCPV c ON c.CpvKey = f.CpvKey
    WHERE f.IsED = 0 AND c.IsITServices = 1
      AND f.WinnerLabel NOT IN (N'Other supplier (name not kept)', N'Supplier not stated')
    GROUP BY f.WinnerLabel)
SELECT TOP (15) WinnerLabel, Lots, Buyers, RANK() OVER (ORDER BY Lots DESC) AS RankByLots
FROM w ORDER BY Lots DESC;

/* Q6  FTS: commitments by department and year, with each department's share of the year (window SUM) */
SELECT f.[Year], d.DepartmentCode, SUM(f.ContractedEUR) AS ContractedEUR,
       CAST(100.0 * SUM(f.ContractedEUR) / SUM(SUM(f.ContractedEUR)) OVER (PARTITION BY f.[Year]) AS DECIMAL(5,1)) AS ShareOfYearPct
FROM dwh.FactFts f JOIN dwh.DimDepartment d ON d.DepartmentKey = f.DepartmentKey
GROUP BY f.[Year], d.DepartmentCode
ORDER BY f.[Year], ContractedEUR DESC;

/* Q7  SIMULATED service desk: SLA by agency and month, with the agency's rank each month */
WITH m AS (
    SELECT a.AgencyName, dd.YearMonth,
           AVG(IIF(r.IsSlaMet = 1, 1.0, 0.0)) AS SlaMet, COUNT(*) AS Requests
    FROM sim.FactServiceRequest r
    JOIN sim.DimAgency a ON a.AgencyKey = r.AgencyKey
    JOIN dwh.DimDate dd ON dd.DateKey = r.DateKey
    WHERE r.IsClosed = 1
    GROUP BY a.AgencyName, dd.YearMonth)
SELECT AgencyName, YearMonth, Requests, CAST(100 * SlaMet AS DECIMAL(5,1)) AS SlaMetPct,
       RANK() OVER (PARTITION BY YearMonth ORDER BY SlaMet DESC) AS RankInMonth
FROM m ORDER BY YearMonth, RankInMonth;
GO
