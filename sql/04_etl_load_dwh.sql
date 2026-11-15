/* =====================================================================================================
   04  ETL in T-SQL: stg (raw text) -> dwh (typed star schema)
   One re-runnable procedure, dwh.usp_LoadWarehouse, in numbered steps:
     1  unify the three TED extracts into one typed award list (#award)
          - dates: legacy "dd/mm/yy" (style 3) and eForms ISO dates (style 23)
          - values: TRY_CAST, so a malformed number becomes NULL instead of failing the load
          - legacy rows without a winner (lot not awarded) are left out
          - eForms rows flagged by the Python parser (DQ-03 / DQ-04, see docs/DATA_QUALITY.md) are left out
     2  currency conversion to EUR with the ECB annual average rate of the publication year
     3  de-duplication of award rows, and one counted value per notice-lot (no double counting of lot values
        when several suppliers win the same lot of a framework agreement)
     4  name resolution: split winner lists ("A---B---C"), normalise, match ref.EntityAlias patterns
     5  dimensions (date, country, CPV, procedure, entity, buyer, department, programme)
     6  facts (FactAward, FactFts) and the SIMULATED service desk
   ===================================================================================================== */
USE EuroDynDW;
GO
DROP PROCEDURE IF EXISTS dwh.usp_LoadWarehouse;
GO
CREATE PROCEDURE dwh.usp_LoadWarehouse
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;
    BEGIN TRANSACTION;

    DELETE FROM dwh.FactAward;  DELETE FROM dwh.FactFts;
    DELETE FROM sim.FactServiceRequest; DELETE FROM sim.SecUserAgency; DELETE FROM sim.DimAgency;
    DELETE FROM dwh.DimBuyer; DELETE FROM dwh.DimCountry; DELETE FROM dwh.DimCPV; DELETE FROM dwh.DimProcedure;
    DELETE FROM dwh.DimEntity; DELETE FROM dwh.DimDepartment; DELETE FROM dwh.DimProgramme; DELETE FROM dwh.DimDate;
    DELETE FROM dwh.EntityNameMap;

    /* ---------- 1. unified award list ---------- */
    CREATE TABLE #award (
        RowId INT IDENTITY(1,1) PRIMARY KEY, SourceSystem NVARCHAR(30), NoticeId VARCHAR(20), LotId NVARCHAR(100),
        AwardRef NVARCHAR(40), PubDate DATE, BuyerName NVARCHAR(2000), BuyerNorm NVARCHAR(400), CountryCode VARCHAR(3),
        BuyerTypeCode VARCHAR(30), CpvCode CHAR(8), ProcedureCode VARCHAR(20), IsFramework BIT, NumberOfOffers INT,
        AwardValue FLOAT, EstValue FLOAT, Currency CHAR(3), Winners NVARCHAR(2000), Title NVARCHAR(400),
        WinnersXml INT NULL,     -- eForms: number of winning tenders in the lot (all suppliers, not only ED)
        FxConverted BIT NOT NULL DEFAULT 0
    );

    INSERT #award (SourceSystem, NoticeId, LotId, AwardRef, PubDate, BuyerName, BuyerNorm, CountryCode, BuyerTypeCode,
                   CpvCode, ProcedureCode, IsFramework, NumberOfOffers, AwardValue, EstValue, Currency, Winners, Title)
    SELECT N'TED legacy CSV', notice_id,
           COALESCE(NULLIF(ID_LOT_AWARDED, N''), NULLIF(ID_LOT, N''), N'1'),
           ISNULL(ID_AWARD, N''),
           TRY_CONVERT(DATE, DT_DISPATCH, 3),
           CAE_NAME, LEFT(buyer_key, 400), ISO_COUNTRY_CODE, 'L:' + ISNULL(CAE_TYPE, N''),
           LEFT(CPV, 8), 'L:' + ISNULL(TOP_TYPE, N''), IIF(B_FRA_AGREEMENT = N'Y', 1, 0),
           TRY_CAST(NUMBER_OFFERS AS INT),
           TRY_CAST(AWARD_VALUE_EURO AS FLOAT),
           COALESCE(TRY_CAST(AWARD_EST_VALUE_EURO AS FLOAT),
                    IIF(TRY_CAST(LOTS_NUMBER AS INT) <= 1, TRY_CAST(VALUE_EURO AS FLOAT), NULL)),
           'EUR',                                   -- the Publications Office already converted legacy values to EUR
           WIN_NAME, IIF(is_ed_raw = N'True', LEFT(TITLE, 400), NULL)
    FROM stg.ted_legacy_awards
    WHERE NULLIF(LTRIM(WIN_NAME), N'') IS NOT NULL;

    INSERT #award (SourceSystem, NoticeId, LotId, AwardRef, PubDate, BuyerName, BuyerNorm, CountryCode, BuyerTypeCode,
                   CpvCode, ProcedureCode, IsFramework, NumberOfOffers, AwardValue, EstValue, Currency, Winners, Title)
    SELECT N'TED eForms XML', notice_id, lot_id, N'', TRY_CONVERT(DATE, publication_date, 23),
           buyer_name, LEFT(buyer_key, 400), buyer_country, 'E:' + ISNULL(buyer_legal_type, N''),
           LEFT(cpv_main, 8), 'E:' + ISNULL(procedure_code, N''),
           IIF(framework LIKE N'fa-%', 1, 0),
           TRY_CAST(n_tenders AS INT),
           TRY_CAST(award_value AS FLOAT), TRY_CAST(est_value AS FLOAT),
           COALESCE(award_currency, est_currency, 'EUR'),
           COALESCE(NULLIF(winner_names, N''), tendering_party_name), LEFT(title, 400)
    FROM stg.ted_eforms_ed_awards
    WHERE ISNULL(dq_excluded, N'') = N'';

    INSERT #award (SourceSystem, NoticeId, LotId, AwardRef, PubDate, BuyerName, BuyerNorm, CountryCode, BuyerTypeCode,
                   CpvCode, ProcedureCode, IsFramework, NumberOfOffers, AwardValue, EstValue, Currency, Winners, Title)
    SELECT N'TED eForms API (notice)', notice_id, N'(notice)', N'', TRY_CONVERT(DATE, publication_date, 23),
           buyer_name, LEFT(buyer_key, 400), buyer_country, 'E:' + ISNULL(buyer_legal_type, N''),
           LEFT(cpv_main, 8), 'E:' + ISNULL(procedure_code, N''), 0,
           IIF(TRY_CAST(lots_with_stats AS INT) = 1, TRY_CAST(n_tenders_min AS INT), NULL),   -- single-lot notices only
           TRY_CAST(total_value AS FLOAT), NULL, COALESCE(total_currency, 'EUR'),
           first_winner, NULL
    FROM stg.ted_eforms_market_notices
    WHERE has_ed <> N'True'                 -- European Dynamics notices come from the XML, lot by lot
      AND notice_id NOT IN (SELECT notice_id FROM stg.ted_eforms_ed_awards);

    UPDATE a SET WinnersXml = TRY_CAST(x.n_winning_tenders_in_lot AS INT)
    FROM #award a JOIN stg.ted_eforms_ed_awards x ON x.notice_id = a.NoticeId AND x.lot_id = a.LotId
    WHERE a.SourceSystem = N'TED eForms XML';

    /* ---------- 2. currency conversion (ECB annual average, publication year; latest year as fallback) ---------- */
    UPDATE a SET AwardValue = a.AwardValue / r.Rate, EstValue = a.EstValue / r.Rate, FxConverted = 1
    FROM #award a
    CROSS APPLY (SELECT TOP (1) TRY_CAST(units_per_eur AS FLOAT) AS Rate
                 FROM stg.ecb_exr_annual e
                 WHERE e.currency = a.Currency AND TRY_CAST(e.[year] AS INT) <= YEAR(a.PubDate)
                 ORDER BY TRY_CAST(e.[year] AS INT) DESC) r
    WHERE a.Currency <> 'EUR';
    -- currency without an ECB reference rate (e.g. MKD): value unknown in EUR -> NULL, never counted as euros
    UPDATE #award SET AwardValue = NULL, EstValue = NULL WHERE Currency <> 'EUR' AND FxConverted = 0;

    /* ---------- 3a. exact duplicates (same notice, lot, award and winner text) ---------- */
    WITH d AS (SELECT RowId, ROW_NUMBER() OVER (PARTITION BY NoticeId, LotId, AwardRef, Winners ORDER BY RowId) AS rn
               FROM #award)
    DELETE FROM #award WHERE RowId IN (SELECT RowId FROM d WHERE rn > 1);

    /* ---------- 4. name resolution ---------- */
    CREATE TABLE #member (RowId INT, RawName NVARCHAR(600), NormName NVARCHAR(600), Ordinal INT, EntityCode VARCHAR(10),
                          Pattern NVARCHAR(100));
    INSERT #member (RowId, RawName, Ordinal)
    SELECT a.RowId, LTRIM(RTRIM(s.value)),
           CHARINDEX(LTRIM(RTRIM(s.value)), REPLACE(a.Winners, N'---', N'|'))
    FROM #award a
    CROSS APPLY STRING_SPLIT(REPLACE(a.Winners, N'---', N'|'), N'|') s
    WHERE LTRIM(RTRIM(s.value)) <> N'';

    CREATE TABLE #names (RawName NVARCHAR(600) NOT NULL, NormName NVARCHAR(600), EntityCode VARCHAR(10), Pattern NVARCHAR(100));
    INSERT #names (RawName) SELECT DISTINCT RawName FROM #member;
    UPDATE #names SET NormName = dwh.fn_NormName(RawName);     -- the UDF runs once per distinct name
    UPDATE n SET EntityCode = ISNULL(m.EntityCode, 'NONE'), Pattern = m.Pattern
    FROM #names n
    OUTER APPLY (SELECT TOP (1) a.EntityCode, a.Pattern FROM ref.EntityAlias a
                 WHERE n.NormName LIKE a.Pattern ORDER BY a.Priority) m;
    UPDATE m SET NormName = n.NormName, EntityCode = n.EntityCode, Pattern = n.Pattern
    FROM #member m JOIN #names n ON n.RawName = m.RawName;

    INSERT dwh.EntityNameMap (RawName, NormName, EntityCode, MatchedPattern, SourceSystem, Occurrences)
    SELECT m.RawName, m.NormName, m.EntityCode, m.Pattern, a.SourceSystem, COUNT(*)
    FROM #member m JOIN #award a ON a.RowId = m.RowId
    WHERE m.EntityCode <> 'NONE'
    GROUP BY m.RawName, m.NormName, m.EntityCode, m.Pattern, a.SourceSystem;

    /* award-level summary: lead ED entity (a member flagged as leader, else the first listed), partners */
    CREATE TABLE #awardEntity (RowId INT PRIMARY KEY, LeadEntity VARCHAR(10), EdMembers INT, OtherMembers INT,
                               FirstOther NVARCHAR(600));
    WITH ranked AS (
        SELECT RowId, EntityCode, NormName,
               ROW_NUMBER() OVER (PARTITION BY RowId
                                  ORDER BY IIF(EntityCode = 'NONE', 1, 0),
                                           IIF(NormName LIKE N'%LEAD%', 0, 1),
                                           IIF(EntityCode IN ('ED-CO', 'ED-XX'), 1, 0), Ordinal) AS rn_ed,
               ROW_NUMBER() OVER (PARTITION BY RowId ORDER BY IIF(EntityCode = 'NONE', 0, 1), Ordinal) AS rn_other
        FROM #member)
    INSERT #awardEntity (RowId, LeadEntity, EdMembers, OtherMembers, FirstOther)
    SELECT RowId,
           MAX(IIF(rn_ed = 1 AND EntityCode <> 'NONE', EntityCode, NULL)),
           SUM(IIF(EntityCode <> 'NONE', 1, 0)),
           SUM(IIF(EntityCode = 'NONE', 1, 0)),
           MAX(IIF(rn_other = 1 AND EntityCode = 'NONE', NormName, NULL))
    FROM ranked GROUP BY RowId;

    /* ---------- 5. dimensions ---------- */
    ;WITH n AS (SELECT TOP (DATEDIFF(DAY, '2016-01-01', '2026-12-31') + 1)
                       ROW_NUMBER() OVER (ORDER BY (SELECT NULL)) - 1 AS i
                FROM sys.all_objects a CROSS JOIN sys.all_objects b),
          d AS (SELECT DATEADD(DAY, i, CAST('2016-01-01' AS DATE)) AS dt FROM n)
    INSERT dwh.DimDate (DateKey, [Date], [Year], Quarter, MonthNo, MonthName, YearMonth, TedFormat)
    SELECT YEAR(dt) * 10000 + MONTH(dt) * 100 + DAY(dt), dt, YEAR(dt), DATEPART(QUARTER, dt), MONTH(dt),
           LEFT(DATENAME(MONTH, dt), 12), CONVERT(CHAR(7), dt, 126),
           IIF(dt < '2023-11-01', N'Legacy TED', N'eForms')
    FROM d;

    INSERT dwh.DimCountry (ISO2, ISO3, CountryName, IsEUMember)
    SELECT iso2, iso3, country_name, TRY_CAST(is_eu_member AS BIT) FROM stg.ref_country;

    INSERT dwh.DimCPV (CpvCode, CpvLabel, DivisionCode, DivisionLabel, GroupCode, GroupLabel, ClassCode, ClassLabel, IsITServices)
    SELECT cpv_code, cpv_label, LEFT(cpv_code, 2), division_label, LEFT(cpv_code, 3), group_label,
           LEFT(cpv_code, 4), class_label, IIF(LEFT(cpv_code, 2) = '72', 1, 0)
    FROM stg.ref_cpv;

    INSERT dwh.DimProcedure (ProcedureLabel, ProcedureFamily, SortOrder)
    SELECT ProcedureLabel, MIN(ProcedureFamily), MIN(SortOrder) FROM ref.[Procedure] GROUP BY ProcedureLabel;

    INSERT dwh.DimEntity (EntityKey, EntityCode, EntityName, EntityCountry, EntityKind, IsED)
    SELECT ROW_NUMBER() OVER (ORDER BY IIF(EntityCode = 'NONE', 0, 1), EntityCode) - 1,   -- 0 = not ED
           EntityCode, EntityName, EntityCountry, EntityKind, IIF(EntityCode = 'NONE', 0, 1)
    FROM ref.Entity;

    /* buyer: one member per normalised name; most frequent spelling, country and type win */
    ;WITH b AS (
        SELECT a.BuyerNorm, a.BuyerName, COALESCE(c2.ISO3, c3.ISO3) AS ISO3,
               ISNULL(bt.BuyerType, N'Not stated') AS BuyerType, ISNULL(bt.IsEU, 0) AS IsEU, ISNULL(bt.SortOrder, 9) AS so
        FROM #award a
        LEFT JOIN dwh.DimCountry c2 ON c2.ISO2 = a.CountryCode
        LEFT JOIN dwh.DimCountry c3 ON c3.ISO3 = a.CountryCode
        LEFT JOIN ref.BuyerType bt ON bt.SourceCode = a.BuyerTypeCode
        WHERE ISNULL(a.BuyerNorm, N'') <> N''),
    bc AS (SELECT b.*, COUNT(*) OVER (PARTITION BY BuyerNorm, BuyerName) AS name_count FROM b),
    pick AS (
        SELECT BuyerNorm, BuyerName, ISO3, BuyerType, IsEU,
               ROW_NUMBER() OVER (PARTITION BY BuyerNorm ORDER BY name_count DESC, BuyerName) AS rn_name,
               ROW_NUMBER() OVER (PARTITION BY BuyerNorm ORDER BY IsEU DESC, so, ISO3) AS rn_type
        FROM bc)
    INSERT dwh.DimBuyer (BuyerNormName, BuyerName, CountryISO3, BuyerType, BuyerGroup, IsEU)
    SELECT n.BuyerNorm, LEFT(n.BuyerName, 400), t.ISO3, t.BuyerType,
           CASE WHEN t.IsEU = 1 AND (n.BuyerNorm LIKE N'%EUROPEAN COMMISSION%' OR n.BuyerNorm LIKE N'%COMMISSION EUROPEENNE%'
                                     OR n.BuyerNorm LIKE N'%EUROPAISCHE KOMMISSION%' OR n.BuyerNorm LIKE N'EC %'
                                     OR n.BuyerNorm LIKE N'%DIRECTORATE GENERAL%' OR n.BuyerNorm LIKE N'%DG %')
                     THEN N'European Commission'
                WHEN t.IsEU = 1 THEN N'EU agency or other EU body'
                ELSE t.BuyerType END,
           t.IsEU
    FROM (SELECT BuyerNorm, BuyerName FROM pick WHERE rn_name = 1) n
    JOIN (SELECT BuyerNorm, ISO3, BuyerType, IsEU FROM pick WHERE rn_type = 1) t ON t.BuyerNorm = n.BuyerNorm;

    INSERT dwh.DimBuyer (BuyerNormName, BuyerName, CountryISO3, BuyerType, BuyerGroup, IsEU)
    VALUES (N'(UNKNOWN)', N'(buyer not stated)', NULL, N'Not stated', N'Not stated', 0);

    /* FTS departments ("DIGIT - Directorate-General for Digital Services") and programmes */
    INSERT dwh.DimDepartment (DepartmentCode, DepartmentName)
    SELECT DISTINCT
           LEFT(LTRIM(RTRIM(IIF(CHARINDEX(N' - ', department) > 0, LEFT(department, CHARINDEX(N' - ', department) - 1), department))), 20),
           LTRIM(RTRIM(IIF(CHARINDEX(N' - ', department) > 0, SUBSTRING(department, CHARINDEX(N' - ', department) + 3, 200), department)))
    FROM (SELECT REPLACE(IIF(department LIKE N'X - %', SUBSTRING(department, 5, 400), ISNULL(NULLIF(department, N''), N'N/A - Not stated')), N'  ', N' ')  /* "X - " = former department */ AS department FROM stg.fts_ed) x;

    INSERT dwh.DimProgramme (ProgrammeName, ProgrammeFamily)
    SELECT p, CASE WHEN p LIKE N'%Horizon%' THEN N'Research (Horizon)'
                   WHEN p LIKE N'%administrative expenditure%' OR p LIKE N'%Information and communication technology%'
                        THEN N'Commission administration and IT'
                   WHEN p LIKE N'%Customs%' OR p LIKE N'%Fiscalis%' THEN N'Customs and taxation'
                   WHEN p LIKE N'%Digital Europe%' OR p LIKE N'%Connecting Europe%' OR p LIKE N'%ISA%' THEN N'Digital programmes'
                   ELSE N'Other programmes' END
    FROM (SELECT DISTINCT ISNULL(NULLIF(programme_name, N''), N'Not stated') AS p FROM stg.fts_ed) x;

    /* ---------- 3b + 6. FactAward ---------- */
    ;WITH f AS (
        SELECT a.*, ae.LeadEntity, ISNULL(ae.EdMembers, 0) AS EdMembers, ISNULL(ae.OtherMembers, 0) AS OtherMembers,
               ae.FirstOther,
               COALESCE(a.AwardValue, a.EstValue) AS ValueEUR,
               CASE WHEN a.AwardValue IS NOT NULL THEN N'Awarded value'
                    WHEN a.EstValue IS NOT NULL THEN N'Estimated value'
                    ELSE N'Missing' END AS ValueSource
        FROM #award a LEFT JOIN #awardEntity ae ON ae.RowId = a.RowId),
    g AS (
        SELECT f.*,
               IIF(ValueEUR > 2e9 OR ValueEUR < 1, 1, 0) AS IsOutlier,
               ROW_NUMBER() OVER (PARTITION BY NoticeId, LotId
                                  ORDER BY IIF(EdMembers > 0, 0, 1), IIF(ValueEUR IS NULL, 1, 0), RowId) AS rn_lot
        FROM f),
    h AS (
        SELECT g.*,
               COALESCE(WinnersXml, COUNT(*) OVER (PARTITION BY NoticeId, LotId)) AS WinnersInLot,
               MAX(IIF(rn_lot = 1 AND IsOutlier = 0, ValueEUR, NULL)) OVER (PARTITION BY NoticeId, LotId) AS LotValue
        FROM g)
    INSERT dwh.FactAward (SourceSystem, NoticeId, LotId, DateKey, BuyerKey, CountryKey, CpvKey, ProcedureKey, EntityKey,
                          IsED, EdRole, PartnerCount, IsFramework, NumberOfOffers, ValueEUR, ValueSource, IsValueCounted,
                          IsValueOutlier, OriginalCurrency, WinnerLabel, Title, WinnersInLot, ValueSplitEUR)
    SELECT g.SourceSystem, g.NoticeId, g.LotId,
           YEAR(g.PubDate) * 10000 + MONTH(g.PubDate) * 100 + DAY(g.PubDate),
           ISNULL(b.BuyerKey, bu.BuyerKey),
           COALESCE(c2.CountryKey, c3.CountryKey),
           cpv.CpvKey,
           ISNULL(pr.ProcedureKey, pu.ProcedureKey),
           ISNULL(e.EntityKey, 0),
           IIF(g.EdMembers > 0, 1, 0),
           CASE WHEN g.EdMembers = 0 THEN N'Other supplier'
                WHEN g.OtherMembers = 0 AND g.EdMembers = 1 THEN N'ED entity alone'
                WHEN g.OtherMembers = 0 THEN N'ED entities together'
                ELSE N'Consortium with partners' END,
           IIF(g.EdMembers > 0, g.OtherMembers, 0),
           g.IsFramework, g.NumberOfOffers,
           CAST(IIF(g.IsOutlier = 1, NULL, g.ValueEUR) AS DECIMAL(18,2)),
           IIF(g.IsOutlier = 1, N'Outlier removed', g.ValueSource),
           IIF(g.rn_lot = 1 AND g.IsOutlier = 0 AND g.ValueEUR IS NOT NULL, 1, 0),
           g.IsOutlier, g.Currency,
           CASE WHEN g.EdMembers > 0 THEN e.EntityName
                WHEN g.FirstOther IS NULL THEN N'Supplier not stated'
                WHEN EXISTS (SELECT 1 FROM ref.LegalFormToken t WHERE N' ' + g.FirstOther + N' ' LIKE N'% ' + t.Token + N' %')
                     -- legal-form spellings unified so "ARHS DEVELOPMENTS S A" and "... SA" are one supplier
                     THEN LEFT(LTRIM(RTRIM(REPLACE(REPLACE(REPLACE(REPLACE(N' ' + g.FirstOther + N' ',
                          N' S A ', N' SA '), N' S P A ', N' SPA '), N' S A R L ', N' SARL '), N' S L ', N' SL '))), 200)
                ELSE N'Other supplier (name not kept)' END,       -- protects sole traders' personal names
           g.Title, g.WinnersInLot,
           CAST(g.LotValue / NULLIF(g.WinnersInLot, 0) AS DECIMAL(18,2))   -- equal split between winning tenders
    FROM h AS g
    LEFT JOIN dwh.DimBuyer b ON b.BuyerNormName = g.BuyerNorm
    CROSS JOIN (SELECT BuyerKey FROM dwh.DimBuyer WHERE BuyerNormName = N'(UNKNOWN)') bu
    LEFT JOIN dwh.DimCountry c2 ON c2.ISO2 = g.CountryCode
    LEFT JOIN dwh.DimCountry c3 ON c3.ISO3 = g.CountryCode
    LEFT JOIN dwh.DimCPV cpv ON cpv.CpvCode = g.CpvCode
    LEFT JOIN ref.[Procedure] rp ON rp.SourceCode = g.ProcedureCode
    LEFT JOIN dwh.DimProcedure pr ON pr.ProcedureLabel = rp.ProcedureLabel
    CROSS JOIN (SELECT ProcedureKey FROM dwh.DimProcedure WHERE ProcedureLabel = N'Not stated') pu
    LEFT JOIN dwh.DimEntity e ON e.EntityCode = g.LeadEntity
    WHERE g.PubDate BETWEEN '2016-01-01' AND '2026-12-31';

    /* ---------- 6b. FactFts (European Dynamics rows of the FTS) ---------- */
    ;WITH s AS (
        SELECT TRY_CAST([year] AS SMALLINT) AS yr, beneficiary_name,
               dwh.fn_NormName(beneficiary_name) AS norm,
               REPLACE(IIF(department LIKE N'X - %', SUBSTRING(department, 5, 400), ISNULL(NULLIF(department, N''), N'N/A - Not stated')), N'  ', N' ')  /* "X - " = former department */ AS department,
               ISNULL(NULLIF(programme_name, N''), N'Not stated') AS programme_name,
               contract_type, expense_type, budget_ref,
               TRY_CAST(contracted_eur AS FLOAT) AS contracted, TRY_CAST(est_consumed_eur AS FLOAT) AS consumed
        FROM stg.fts_ed)
    INSERT dwh.FactFts ([Year], DateKey, EntityKey, DepartmentKey, ProgrammeKey, ContractType, ExpenseType, IsConsortium,
                        ContractedEUR, EstConsumedEUR, BudgetRef)
    SELECT s.yr, s.yr * 10000 + 101, ISNULL(e.EntityKey, 0), d.DepartmentKey, p.ProgrammeKey,
           LEFT(s.contract_type, 80), LEFT(s.expense_type, 30), IIF(s.norm LIKE N'CONSORTIUM%', 1, 0),
           CAST(ISNULL(s.contracted, 0) AS DECIMAL(18,2)), CAST(s.consumed AS DECIMAL(18,2)), LEFT(s.budget_ref, 60)
    FROM s
    OUTER APPLY (SELECT TOP (1) a.EntityCode FROM ref.EntityAlias a WHERE s.norm LIKE a.Pattern ORDER BY a.Priority) m
    LEFT JOIN dwh.DimEntity e ON e.EntityCode = m.EntityCode
    JOIN dwh.DimDepartment d ON d.DepartmentName = LTRIM(RTRIM(IIF(CHARINDEX(N' - ', s.department) > 0,
                                     SUBSTRING(s.department, CHARINDEX(N' - ', s.department) + 3, 200), s.department)))
                            AND d.DepartmentCode = LEFT(LTRIM(RTRIM(IIF(CHARINDEX(N' - ', s.department) > 0,
                                     LEFT(s.department, CHARINDEX(N' - ', s.department) - 1), s.department))), 20)
    JOIN dwh.DimProgramme p ON p.ProgrammeName = s.programme_name
    WHERE s.yr BETWEEN 2016 AND 2026;

    INSERT dwh.EntityNameMap (RawName, NormName, EntityCode, MatchedPattern, SourceSystem, Occurrences)
    SELECT f.beneficiary_name, dwh.fn_NormName(f.beneficiary_name), ISNULL(m.EntityCode, 'NONE'), m.Pattern, N'FTS', COUNT(*)
    FROM stg.fts_ed f
    OUTER APPLY (SELECT TOP (1) a.EntityCode, a.Pattern FROM ref.EntityAlias a
                 WHERE dwh.fn_NormName(f.beneficiary_name) LIKE a.Pattern ORDER BY a.Priority) m
    GROUP BY f.beneficiary_name, m.EntityCode, m.Pattern;

    /* ---------- 6c. SIMULATED service desk ---------- */
    INSERT sim.DimAgency (AgencyCode, AgencyName, Ministry) SELECT agency_code, agency_name, ministry FROM stg.sim_agency;
    INSERT sim.SecUserAgency (UserPrincipalName, AgencyCode) SELECT user_principal_name, agency_code FROM stg.sim_user_agency;
    INSERT sim.FactServiceRequest (RequestId, DateKey, AgencyKey, ServiceName, Channel, Priority, OpenedAt, ClosedAt,
                                   SlaTargetHours, ResolutionHours, IsClosed, IsSlaMet, Satisfaction)
    SELECT r.request_id, CONVERT(INT, CONVERT(CHAR(8), TRY_CONVERT(DATETIME2(0), r.opened_at, 120), 112)), a.AgencyKey,
           r.service, r.channel, r.priority, TRY_CONVERT(DATETIME2(0), r.opened_at, 120),
           TRY_CONVERT(DATETIME2(0), NULLIF(r.closed_at, N''), 120),
           TRY_CAST(r.sla_target_hours AS SMALLINT), TRY_CAST(NULLIF(r.resolution_hours, N'') AS DECIMAL(9,1)),
           IIF(r.status = N'Closed', 1, 0),
           CASE WHEN r.status <> N'Closed' THEN NULL
                WHEN TRY_CAST(r.resolution_hours AS FLOAT) <= TRY_CAST(r.sla_target_hours AS FLOAT) THEN 1 ELSE 0 END,
           TRY_CAST(TRY_CAST(NULLIF(r.satisfaction, N'') AS FLOAT) AS TINYINT)
    FROM stg.sim_service_request r JOIN sim.DimAgency a ON a.AgencyCode = r.agency_code;

    COMMIT TRANSACTION;
END;
GO
EXEC dwh.usp_LoadWarehouse;
GO
