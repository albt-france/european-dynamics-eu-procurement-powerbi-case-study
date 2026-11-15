# Data dictionary

## Sources

| Source | What | Period | Access | Licence |
|---|---|---|---|---|
| TED - Contract award notices (CSV subset), Publications Office, data.europa.eu dataset `ted-csv` | one row per award | 2016 - Oct 2023 | yearly zip, `src/download_ted.py` | (c) EU, reuse with attribution (Decision 2011/833/EU) |
| TED Search API v3 (`api.ted.europa.eu/v3/notices/search`) + notice XML (`ted.europa.eu/en/notice/{id}/xml`) | eForms notices: ED lots (XML) and CPV 72 market context (search fields) | Nov 2023 - 13 Nov 2026 | anonymous, paged, 1 request/s | same |
| Financial Transparency System (FTS), European Commission | legal commitments by beneficiary, department, programme | 2016 - 2025 | yearly XLSX, `src/download_fts.py` | same |
| ECB euro reference rates (data-api.ecb.europa.eu, EXR annual averages) | currency conversion of non-EUR eForms values | 2016 - 2026 | CSV API | ECB, reuse with source |
| CPV 2008 code list (TED) | CPV labels and hierarchy | - | XLSX | (c) EU |
| European Dynamics website (eurodyn.com) | company facts quoted in the report, *as stated by European Dynamics* | read 15 Nov 2026 | public pages | quoted, not redistributed |

Retrieved on 15 November 2026. Personal data: contact points, addresses, e-mails and phone numbers of buyers and winners are never read; supplier names that do not look like an organisation are replaced by *Other supplier (name not kept)*.

## Star schema (SQL Server `EuroDynDW`, Power BI model)

Relationships (one-to-many, single direction): `FactAward[DateKey]` -> `DimDate[DateKey]`; `FactAward[BuyerKey]` -> `DimBuyer[BuyerKey]`; `FactAward[CountryKey]` -> `DimCountry[CountryKey]`; `FactAward[CpvKey]` -> `DimCPV[CpvKey]`; `FactAward[ProcedureKey]` -> `DimProcedure[ProcedureKey]`; `FactAward[EntityKey]` -> `DimEntity[EntityKey]`; `FactFts[DateKey]` -> `DimDate[DateKey]`; `FactFts[EntityCode]` -> `DimEntity[EntityCode]`; `FactFts[Department]` -> `DimDepartment[Department]`; `FactFts[Programme]` -> `DimProgramme[Programme]`; `FactServiceRequest[DateKey]` -> `DimDate[DateKey]`; `FactServiceRequest[AgencyKey]` -> `DimAgency[AgencyKey]`.

### `dwh.DimBuyer` (445 rows)

Contracting authorities (normalised names).

| Column | SQL type |
|---|---|
| BuyerKey | int |
| BuyerNormName | nvarchar |
| BuyerName | nvarchar |
| CountryISO3 | char |
| BuyerType | nvarchar |
| BuyerGroup | nvarchar |
| IsEU | bit |

### `dwh.DimCountry` (42 rows)

Country of the buyer.

| Column | SQL type |
|---|---|
| CountryKey | int |
| ISO2 | char |
| ISO3 | char |
| CountryName | nvarchar |
| IsEUMember | bit |

### `dwh.DimCPV` (148 rows)

Common Procurement Vocabulary, hierarchy Division > Group > Class > Code.

| Column | SQL type |
|---|---|
| CpvKey | int |
| CpvCode | char |
| CpvLabel | nvarchar |
| DivisionCode | char |
| DivisionLabel | nvarchar |
| GroupCode | char |
| GroupLabel | nvarchar |
| ClassCode | char |
| ClassLabel | nvarchar |
| IsITServices | bit |

### `dwh.DimDate` (4,018 rows)

Calendar 2016-2026 (marked as date table).

| Column | SQL type |
|---|---|
| DateKey | int |
| Date | date |
| Year | smallint |
| Quarter | tinyint |
| MonthNo | tinyint |
| MonthName | nvarchar |
| YearMonth | char |
| TedFormat | nvarchar |

### `dwh.DimDepartment` (57 rows)

Commission departments (FTS).

| Column | SQL type |
|---|---|
| DepartmentKey | int |
| DepartmentCode | nvarchar |
| DepartmentName | nvarchar |

### `dwh.DimEntity` (9 rows)

European Dynamics entities after name resolution (0 = other supplier).

| Column | SQL type |
|---|---|
| EntityKey | int |
| EntityCode | varchar |
| EntityName | nvarchar |
| EntityCountry | char |
| EntityKind | nvarchar |
| IsED | bit |

### `dwh.DimProcedure` (10 rows)

Procurement procedure (legacy TED and eForms codes mapped to one list).

| Column | SQL type |
|---|---|
| ProcedureKey | int |
| ProcedureLabel | nvarchar |
| ProcedureFamily | nvarchar |
| SortOrder | tinyint |

### `dwh.DimProgramme` (97 rows)

EU budget programmes (FTS).

| Column | SQL type |
|---|---|
| ProgrammeKey | int |
| ProgrammeName | nvarchar |
| ProgrammeFamily | nvarchar |

### `dwh.EntityNameMap` (78 rows)

Audit of name resolution: raw spelling -> entity (documentation page).

| Column | SQL type |
|---|---|
| RawName | nvarchar |
| NormName | nvarchar |
| EntityCode | varchar |
| MatchedPattern | nvarchar |
| SourceSystem | nvarchar |
| Occurrences | int |

### `dwh.FactAward` (6,038 rows)

One row per published award (notice x lot x winning tender). PUBLIC DATA, TED.

| Column | SQL type |
|---|---|
| AwardKey | int |
| SourceSystem | nvarchar |
| NoticeId | varchar |
| LotId | nvarchar |
| DateKey | int |
| BuyerKey | int |
| CountryKey | int |
| CpvKey | int |
| ProcedureKey | int |
| EntityKey | int |
| IsED | bit |
| EdRole | nvarchar |
| PartnerCount | smallint |
| IsFramework | bit |
| NumberOfOffers | int |
| ValueEUR | decimal |
| ValueSource | nvarchar |
| IsValueCounted | bit |
| IsValueOutlier | bit |
| OriginalCurrency | char |
| WinnerLabel | nvarchar |
| Title | nvarchar |
| WinnersInLot | smallint |
| ValueSplitEUR | decimal |

### `dwh.FactFts` (5,549 rows)

Financial Transparency System, European Dynamics rows: legal commitments by year. PUBLIC DATA.

| Column | SQL type |
|---|---|
| FtsKey | int |
| Year | smallint |
| DateKey | int |
| EntityKey | int |
| DepartmentKey | int |
| ProgrammeKey | int |
| ContractType | nvarchar |
| ExpenseType | nvarchar |
| IsConsortium | bit |
| ContractedEUR | decimal |
| EstConsumedEUR | decimal |
| BudgetRef | nvarchar |

### `sim.DimAgency` (6 rows)

SIMULATED agencies of the fictional ministry. RLS filters this table.

| Column | SQL type |
|---|---|
| AgencyKey | int |
| AgencyCode | varchar |
| AgencyName | nvarchar |
| Ministry | nvarchar |

### `sim.FactServiceRequest` (48,000 rows)

SIMULATED citizen requests of a fictional ministry (RLS demo).

| Column | SQL type |
|---|---|
| RequestId | varchar |
| DateKey | int |
| AgencyKey | int |
| ServiceName | nvarchar |
| Channel | nvarchar |
| Priority | nvarchar |
| OpenedAt | datetime2 |
| ClosedAt | datetime2 |
| SlaTargetHours | smallint |
| ResolutionHours | decimal |
| IsClosed | bit |
| IsSlaMet | bit |
| Satisfaction | tinyint |

### `sim.SecUserAgency` (8 rows)

SIMULATED RLS mapping: user principal name -> agency (fictional .example accounts).

| Column | SQL type |
|---|---|
| UserPrincipalName | nvarchar |
| AgencyCode | varchar |

## Power BI-only tables

* `FactFts`, `DimDepartment`, `DimProgramme`: built in Power Query from the FTS extract (second source; PostgreSQL design, CSV fallback) - see `powerquery/FtsStaging.pq`. `FactFts` relates to `DimEntity` on `EntityCode` and to the two FTS dimensions on their text keys.
* `Time Calc` (calculation group), `Axis` (field parameter), `ML Feature Importance`, `ML Metrics`, `QualityChecks`, `_Measures`.
