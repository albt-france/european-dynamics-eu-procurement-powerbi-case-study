/* =====================================================================================================
   03  Star schema (dwh) - tables, keys and indexes
   Grain
     dwh.FactAward    one row per published award: notice x lot x winning tender (legacy CSV and eForms XML);
                      eForms market context from the search API is at notice level (LotId = '(notice)').
     dwh.FactFts      one row per FTS line: year x legal commitment x budget line x beneficiary.
     sim.FactServiceRequest  one SIMULATED citizen request.
   Index choices (data are small - thousands of rows - so indexes serve the ETL joins and the DirectQuery
   fallback rather than import refresh):
     * every dimension has a narrow INT surrogate key, clustered (dense, ever-increasing, cheap joins);
     * natural keys get a UNIQUE nonclustered index: the ETL looks them up when it resolves surrogate keys,
       and the constraint stops duplicate members (the classic cause of many-to-many relationships in Power BI);
     * facts get a nonclustered index per foreign key used to filter (date, buyer, entity) with the measures
       INCLUDEd, so the typical "value by year for European Dynamics" query is a covering seek.
     * no clustered columnstore: SQL Server 2016 LocalDB/Express supports it, but at < 100k rows a rowstore is
       simpler and just as fast (documented in docs/PERFORMANCE.md).
   ===================================================================================================== */
USE EuroDynDW;
GO
DROP FUNCTION IF EXISTS dwh.fn_NormName;
GO
/* Normalised organisation name: upper case, punctuation -> space, single spaces.
   Scalar UDFs are slow row by row on big tables; here it runs once per distinct name in the ETL. */
CREATE FUNCTION dwh.fn_NormName (@s NVARCHAR(4000))
RETURNS NVARCHAR(4000)
WITH SCHEMABINDING
AS
BEGIN
    DECLARE @r NVARCHAR(4000) = UPPER(ISNULL(@s, N''));
    SET @r = REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(@r,
             N'.', N' '), N',', N' '), N'(', N' '), N')', N' '), N'-', N' '), N'&', N' '), N'/', N' '), N'"', N' '), N'''', N' '), N'*', N' ');
    SET @r = REPLACE(REPLACE(REPLACE(@r, NCHAR(9), N' '), NCHAR(10), N' '), NCHAR(13), N' ');
    WHILE CHARINDEX(N'  ', @r) > 0 SET @r = REPLACE(@r, N'  ', N' ');
    RETURN LTRIM(RTRIM(@r));
END;
GO

DROP TABLE IF EXISTS dwh.FactAward;
DROP TABLE IF EXISTS dwh.FactFts;
DROP TABLE IF EXISTS sim.FactServiceRequest;
DROP TABLE IF EXISTS sim.SecUserAgency;
DROP TABLE IF EXISTS sim.DimAgency;
DROP TABLE IF EXISTS dwh.DimDate;
DROP TABLE IF EXISTS dwh.DimBuyer;
DROP TABLE IF EXISTS dwh.DimCountry;
DROP TABLE IF EXISTS dwh.DimCPV;
DROP TABLE IF EXISTS dwh.DimProcedure;
DROP TABLE IF EXISTS dwh.DimEntity;
DROP TABLE IF EXISTS dwh.DimDepartment;
DROP TABLE IF EXISTS dwh.DimProgramme;
DROP TABLE IF EXISTS dwh.EntityNameMap;
GO

CREATE TABLE dwh.DimDate (
    DateKey      INT          NOT NULL CONSTRAINT PK_DimDate PRIMARY KEY,   -- yyyymmdd
    [Date]       DATE         NOT NULL CONSTRAINT UQ_DimDate_Date UNIQUE,
    [Year]       SMALLINT     NOT NULL,
    Quarter      TINYINT      NOT NULL,
    MonthNo      TINYINT      NOT NULL,
    MonthName    NVARCHAR(12) NOT NULL,
    YearMonth    CHAR(7)      NOT NULL,
    TedFormat    NVARCHAR(20) NOT NULL       -- 'Legacy TED' before 2023-11-01, 'eForms' after (format change)
);

CREATE TABLE dwh.DimCountry (
    CountryKey   INT IDENTITY(1,1) CONSTRAINT PK_DimCountry PRIMARY KEY,
    ISO2         CHAR(2)      NOT NULL CONSTRAINT UQ_DimCountry_ISO2 UNIQUE,
    ISO3         CHAR(3)      NOT NULL CONSTRAINT UQ_DimCountry_ISO3 UNIQUE,
    CountryName  NVARCHAR(60) NOT NULL,
    IsEUMember   BIT          NOT NULL
);

CREATE TABLE dwh.DimBuyer (
    BuyerKey     INT IDENTITY(1,1) CONSTRAINT PK_DimBuyer PRIMARY KEY,
    BuyerNormName NVARCHAR(400) NOT NULL,
    BuyerName    NVARCHAR(400) NOT NULL,      -- most frequent spelling
    CountryISO3  CHAR(3)      NULL,
    BuyerType    NVARCHAR(60) NOT NULL,
    BuyerGroup   NVARCHAR(80) NOT NULL,       -- 'European Commission', 'EU agency or body', or the buyer type
    IsEU         BIT          NOT NULL
);
CREATE UNIQUE INDEX UX_DimBuyer_Norm ON dwh.DimBuyer (BuyerNormName);

CREATE TABLE dwh.DimCPV (
    CpvKey        INT IDENTITY(1,1) CONSTRAINT PK_DimCPV PRIMARY KEY,
    CpvCode       CHAR(8)       NOT NULL CONSTRAINT UQ_DimCPV_Code UNIQUE,
    CpvLabel      NVARCHAR(300) NOT NULL,
    DivisionCode  CHAR(2)       NOT NULL,
    DivisionLabel NVARCHAR(300) NOT NULL,
    GroupCode     CHAR(3)       NOT NULL,
    GroupLabel    NVARCHAR(300) NOT NULL,
    ClassCode     CHAR(4)       NOT NULL,
    ClassLabel    NVARCHAR(300) NOT NULL,
    IsITServices  BIT           NOT NULL        -- division 72
);

CREATE TABLE dwh.DimProcedure (
    ProcedureKey    INT IDENTITY(1,1) CONSTRAINT PK_DimProcedure PRIMARY KEY,
    ProcedureLabel  NVARCHAR(80) NOT NULL CONSTRAINT UQ_DimProcedure UNIQUE,
    ProcedureFamily NVARCHAR(40) NOT NULL,
    SortOrder       TINYINT      NOT NULL
);

CREATE TABLE dwh.DimEntity (
    EntityKey     INT           NOT NULL CONSTRAINT PK_DimEntity PRIMARY KEY,   -- 0 = not European Dynamics
    EntityCode    VARCHAR(10)   NOT NULL CONSTRAINT UQ_DimEntity UNIQUE,
    EntityName    NVARCHAR(120) NOT NULL,
    EntityCountry CHAR(3)       NULL,
    EntityKind    NVARCHAR(40)  NOT NULL,
    IsED          BIT           NOT NULL
);

/* Audit of name resolution: every distinct raw name -> entity (kept for the report's documentation page) */
CREATE TABLE dwh.EntityNameMap (
    RawName      NVARCHAR(600) NOT NULL,
    NormName     NVARCHAR(600) NOT NULL,
    EntityCode   VARCHAR(10)   NOT NULL,
    MatchedPattern NVARCHAR(100) NULL,
    SourceSystem NVARCHAR(30)  NOT NULL,
    Occurrences  INT           NOT NULL
);

CREATE TABLE dwh.DimDepartment (
    DepartmentKey  INT IDENTITY(1,1) CONSTRAINT PK_DimDepartment PRIMARY KEY,
    DepartmentCode NVARCHAR(20)  NOT NULL CONSTRAINT UQ_DimDepartment UNIQUE,
    DepartmentName NVARCHAR(200) NOT NULL
);

CREATE TABLE dwh.DimProgramme (
    ProgrammeKey   INT IDENTITY(1,1) CONSTRAINT PK_DimProgramme PRIMARY KEY,
    ProgrammeName  NVARCHAR(300) NOT NULL CONSTRAINT UQ_DimProgramme UNIQUE,
    ProgrammeFamily NVARCHAR(60) NOT NULL
);

CREATE TABLE dwh.FactAward (
    AwardKey          INT IDENTITY(1,1) CONSTRAINT PK_FactAward PRIMARY KEY,
    SourceSystem      NVARCHAR(30)  NOT NULL,
    NoticeId          VARCHAR(20)   NOT NULL,
    LotId             NVARCHAR(100) NOT NULL,
    DateKey           INT           NOT NULL CONSTRAINT FK_Award_Date REFERENCES dwh.DimDate (DateKey),
    BuyerKey          INT           NOT NULL CONSTRAINT FK_Award_Buyer REFERENCES dwh.DimBuyer (BuyerKey),
    CountryKey        INT           NULL     CONSTRAINT FK_Award_Country REFERENCES dwh.DimCountry (CountryKey),
    CpvKey            INT           NULL     CONSTRAINT FK_Award_CPV REFERENCES dwh.DimCPV (CpvKey),
    ProcedureKey      INT           NOT NULL CONSTRAINT FK_Award_Procedure REFERENCES dwh.DimProcedure (ProcedureKey),
    EntityKey         INT           NOT NULL CONSTRAINT FK_Award_Entity REFERENCES dwh.DimEntity (EntityKey),
    IsED              BIT           NOT NULL,
    EdRole            NVARCHAR(40)  NOT NULL,
    PartnerCount      SMALLINT      NOT NULL,
    IsFramework       BIT           NOT NULL,
    NumberOfOffers    INT           NULL,
    ValueEUR          DECIMAL(18,2) NULL,    -- awarded value, else lot / notice estimate (see ValueSource)
    ValueSource       NVARCHAR(30)  NOT NULL,
    IsValueCounted    BIT           NOT NULL, -- 1 = first row of its notice-lot and not an outlier (no double count)
    IsValueOutlier    BIT           NOT NULL,
    OriginalCurrency  CHAR(3)       NULL,
    WinnerLabel       NVARCHAR(200) NOT NULL,
    Title             NVARCHAR(400) NULL,    -- kept for European Dynamics awards only
    WinnersInLot      SMALLINT      NULL,    -- winning tenders in the same lot (multi-supplier framework > 1)
    ValueSplitEUR     DECIMAL(18,2) NULL     -- lot value / WinnersInLot: sums to the lot value over its winners
);
CREATE INDEX IX_FactAward_Date   ON dwh.FactAward (DateKey)   INCLUDE (ValueSplitEUR, IsED, EntityKey, NumberOfOffers);
CREATE INDEX IX_FactAward_Buyer  ON dwh.FactAward (BuyerKey)  INCLUDE (ValueSplitEUR, IsED);
CREATE INDEX IX_FactAward_Entity ON dwh.FactAward (EntityKey) INCLUDE (DateKey, ValueSplitEUR);
CREATE INDEX IX_FactAward_IsED   ON dwh.FactAward (IsED, BuyerKey);   -- "ED rows by buyer" (ranking, tooltips)
CREATE INDEX IX_FactAward_Notice ON dwh.FactAward (NoticeId, LotId);

CREATE TABLE dwh.FactFts (
    FtsKey            INT IDENTITY(1,1) CONSTRAINT PK_FactFts PRIMARY KEY,
    [Year]            SMALLINT      NOT NULL,
    DateKey           INT           NOT NULL CONSTRAINT FK_Fts_Date REFERENCES dwh.DimDate (DateKey),  -- 1 January of the year
    EntityKey         INT           NOT NULL CONSTRAINT FK_Fts_Entity REFERENCES dwh.DimEntity (EntityKey),
    DepartmentKey     INT           NOT NULL CONSTRAINT FK_Fts_Department REFERENCES dwh.DimDepartment (DepartmentKey),
    ProgrammeKey      INT           NOT NULL CONSTRAINT FK_Fts_Programme REFERENCES dwh.DimProgramme (ProgrammeKey),
    ContractType      NVARCHAR(80)  NULL,
    ExpenseType       NVARCHAR(30)  NULL,
    IsConsortium      BIT           NOT NULL,
    ContractedEUR     DECIMAL(18,2) NOT NULL,
    EstConsumedEUR    DECIMAL(18,2) NULL,
    BudgetRef         NVARCHAR(60)  NULL
);
CREATE INDEX IX_FactFts_Date ON dwh.FactFts (DateKey) INCLUDE (ContractedEUR, DepartmentKey);

/* ---------------- SIMULATED e-Government service desk (fictional) ---------------- */
CREATE TABLE sim.DimAgency (
    AgencyKey   INT IDENTITY(1,1) CONSTRAINT PK_DimAgency PRIMARY KEY,
    AgencyCode  VARCHAR(10)   NOT NULL CONSTRAINT UQ_DimAgency UNIQUE,
    AgencyName  NVARCHAR(100) NOT NULL,
    Ministry    NVARCHAR(100) NOT NULL
);
CREATE TABLE sim.SecUserAgency (           -- RLS mapping: who may see which agency (fictional .example accounts)
    UserPrincipalName NVARCHAR(200) NOT NULL,
    AgencyCode  VARCHAR(10) NOT NULL CONSTRAINT FK_Sec_Agency REFERENCES sim.DimAgency (AgencyCode),
    CONSTRAINT PK_SecUserAgency PRIMARY KEY (UserPrincipalName, AgencyCode)
);
CREATE TABLE sim.FactServiceRequest (
    RequestId        VARCHAR(12)   NOT NULL CONSTRAINT PK_FactServiceRequest PRIMARY KEY,
    DateKey          INT           NOT NULL CONSTRAINT FK_Sr_Date REFERENCES dwh.DimDate (DateKey),
    AgencyKey        INT           NOT NULL CONSTRAINT FK_Sr_Agency REFERENCES sim.DimAgency (AgencyKey),
    ServiceName      NVARCHAR(60)  NOT NULL,
    Channel          NVARCHAR(20)  NOT NULL,
    Priority         NVARCHAR(10)  NOT NULL,
    OpenedAt         DATETIME2(0)  NOT NULL,
    ClosedAt         DATETIME2(0)  NULL,
    SlaTargetHours   SMALLINT      NOT NULL,
    ResolutionHours  DECIMAL(9,1)  NULL,
    IsClosed         BIT           NOT NULL,
    IsSlaMet         BIT           NULL,
    Satisfaction     TINYINT       NULL
);
CREATE INDEX IX_Sr_Agency_Date ON sim.FactServiceRequest (AgencyKey, DateKey) INCLUDE (IsSlaMet, ResolutionHours);
GO
