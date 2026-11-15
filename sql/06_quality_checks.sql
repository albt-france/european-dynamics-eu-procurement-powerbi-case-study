/* =====================================================================================================
   06  Data-quality checks: row counts, reconciliations, orphan keys, duplicates
   Results go to qa.CheckResult (exported to data/processed/qa_checks.csv and shown on the report's hidden
   documentation page). Status: PASS / WARN (explained limitation) / FAIL (must be fixed before publishing).
   ===================================================================================================== */
USE EuroDynDW;
GO
DROP TABLE IF EXISTS qa.CheckResult;
CREATE TABLE qa.CheckResult (
    CheckId   VARCHAR(6)    NOT NULL PRIMARY KEY,
    CheckName NVARCHAR(120) NOT NULL,
    Actual    DECIMAL(18,2) NULL,
    Expected  NVARCHAR(60)  NOT NULL,
    Status    VARCHAR(4)    NOT NULL,
    Note      NVARCHAR(300) NULL
);
GO
DECLARE @v DECIMAL(18,2), @w DECIMAL(18,2);

-- QA01 every year 2016-2025 has at least one European Dynamics award
SELECT @v = COUNT(*) FROM (SELECT d.[Year] FROM dwh.DimDate d WHERE d.[Year] BETWEEN 2016 AND 2025 GROUP BY d.[Year]
                           HAVING NOT EXISTS (SELECT 1 FROM dwh.FactAward f JOIN dwh.DimDate x ON x.DateKey = f.DateKey
                                              WHERE f.IsED = 1 AND x.[Year] = d.[Year])) y;
INSERT qa.CheckResult VALUES ('QA01', N'Years 2016-2025 without any European Dynamics award', @v, N'0', IIF(@v = 0, 'PASS', 'WARN'), NULL);

-- QA02 legacy rows: staging rows with a winner = fact rows + exact duplicates removed
SELECT @v = COUNT(*) FROM stg.ted_legacy_awards WHERE NULLIF(LTRIM(WIN_NAME), N'') IS NOT NULL;
SELECT @w = COUNT(*) FROM dwh.FactAward WHERE SourceSystem = N'TED legacy CSV';
INSERT qa.CheckResult VALUES ('QA02', N'Legacy award rows removed as exact duplicates (staging - fact)', @v - @w, N'small, explained',
       IIF(@v - @w >= 0 AND @v - @w < 0.02 * @v, 'PASS', 'WARN'), CONCAT(N'staging ', CAST(@v AS INT), N' -> fact ', CAST(@w AS INT)));

-- QA03 FTS reconciliation: total contracted amount fact = staging
SELECT @v = SUM(TRY_CAST(contracted_eur AS FLOAT)) FROM stg.fts_ed WHERE TRY_CAST([year] AS INT) BETWEEN 2016 AND 2026;
SELECT @w = SUM(ContractedEUR) FROM dwh.FactFts;
INSERT qa.CheckResult VALUES ('QA03', N'FTS contracted EUR: fact minus staging', ROUND(@w - @v, 0), N'0 (+/- rounding)',
       IIF(ABS(@w - @v) < 100, 'PASS', 'FAIL'), CONCAT(N'fact ', FORMAT(@w, 'N0'), N' EUR'));

-- QA04 orphan / missing keys in FactAward
SELECT @v = COUNT(*) FROM dwh.FactAward WHERE CpvKey IS NULL;
INSERT qa.CheckResult VALUES ('QA04', N'Award rows without a CPV key', @v, N'0', IIF(@v = 0, 'PASS', 'FAIL'), NULL);
SELECT @v = COUNT(*) FROM dwh.FactAward WHERE CountryKey IS NULL;
INSERT qa.CheckResult VALUES ('QA05', N'Award rows without a buyer country', @v, N'< 1% of rows',
       IIF(@v < 0.01 * (SELECT COUNT(*) FROM dwh.FactAward), 'PASS', 'WARN'), NULL);
SELECT @v = COUNT(*) FROM dwh.FactAward f JOIN dwh.DimBuyer b ON b.BuyerKey = f.BuyerKey WHERE b.BuyerNormName = N'(UNKNOWN)';
INSERT qa.CheckResult VALUES ('QA06', N'Award rows with an unknown buyer', @v, N'0', IIF(@v = 0, 'PASS', 'WARN'), NULL);

-- QA07 no double counting: at most one counted value per notice-lot
SELECT @v = COUNT(*) FROM (SELECT NoticeId, LotId FROM dwh.FactAward WHERE IsValueCounted = 1
                           GROUP BY NoticeId, LotId HAVING COUNT(*) > 1) d;
INSERT qa.CheckResult VALUES ('QA07', N'Notice-lots with more than one counted value', @v, N'0', IIF(@v = 0, 'PASS', 'FAIL'), NULL);

-- QA08 outliers removed from value sums
SELECT @v = COUNT(*) FROM dwh.FactAward WHERE IsValueOutlier = 1;
INSERT qa.CheckResult VALUES ('QA08', N'Award values removed as outliers (> EUR 2 bn or < EUR 1)', @v, N'reported',
       'PASS', N'kept as rows (counted as awards), value set to NULL');

-- QA09 European Dynamics awards with a value
SELECT @v = 100.0 * AVG(IIF(ValueEUR IS NULL, 1.0, 0.0)) FROM dwh.FactAward WHERE IsED = 1;
INSERT qa.CheckResult VALUES ('QA09', N'% of European Dynamics award rows without any value', @v, N'reported',
       IIF(@v < 30, 'PASS', 'WARN'), N'values withheld or not published by the buyer');

-- QA10 eForms rows excluded by the parser rules DQ-03 / DQ-04
SELECT @v = COUNT(*) FROM stg.ted_eforms_ed_awards WHERE ISNULL(dq_excluded, N'') <> N'';
INSERT qa.CheckResult VALUES ('QA10', N'eForms rows excluded (winner reference = buyer''s service provider)', @v, N'reported',
       'PASS', N'see docs/DATA_QUALITY.md, DQ-03 and DQ-04');

-- QA11 name resolution coverage
SELECT @v = COUNT(DISTINCT RawName) FROM dwh.EntityNameMap WHERE EntityCode <> 'NONE';
INSERT qa.CheckResult VALUES ('QA11', N'Distinct raw spellings resolved to a European Dynamics entity', @v, N'reported', 'PASS', NULL);
SELECT @v = 100.0 * AVG(IIF(e.EntityCode IN ('ED-XX', 'ED-CO'), 1.0, 0.0))
FROM dwh.FactAward f JOIN dwh.DimEntity e ON e.EntityKey = f.EntityKey WHERE f.IsED = 1;
INSERT qa.CheckResult VALUES ('QA12', N'% of ED awards where the entity is not specified', @v, N'< 10%', IIF(@v < 10, 'PASS', 'WARN'), NULL);

-- QA13 date dimension continuity
SELECT @v = DATEDIFF(DAY, MIN([Date]), MAX([Date])) + 1 - COUNT(*) FROM dwh.DimDate;
INSERT qa.CheckResult VALUES ('QA13', N'Missing days in DimDate', @v, N'0', IIF(@v = 0, 'PASS', 'FAIL'), NULL);

-- QA14 procedures not mapped
SELECT @v = COUNT(*) FROM dwh.FactAward f JOIN dwh.DimProcedure p ON p.ProcedureKey = f.ProcedureKey WHERE p.ProcedureLabel = N'Not stated';
INSERT qa.CheckResult VALUES ('QA14', N'Award rows with procedure not stated', @v, N'< 1% of rows',
       IIF(@v < 0.01 * (SELECT COUNT(*) FROM dwh.FactAward), 'PASS', 'WARN'), NULL);

-- QA15 SIMULATED data: SLA flag present for every closed request and only for those
SELECT @v = COUNT(*) FROM sim.FactServiceRequest WHERE (IsClosed = 1 AND IsSlaMet IS NULL) OR (IsClosed = 0 AND IsSlaMet IS NOT NULL);
INSERT qa.CheckResult VALUES ('QA15', N'SIMULATED requests with an inconsistent SLA flag', @v, N'0', IIF(@v = 0, 'PASS', 'FAIL'), NULL);

-- QA16 RLS mapping: every agency has at least one user
SELECT @v = COUNT(*) FROM sim.DimAgency a WHERE NOT EXISTS (SELECT 1 FROM sim.SecUserAgency s WHERE s.AgencyCode = a.AgencyCode);
INSERT qa.CheckResult VALUES ('QA16', N'Agencies without any RLS user (SIMULATED)', @v, N'0', IIF(@v = 0, 'PASS', 'FAIL'), NULL);
GO
