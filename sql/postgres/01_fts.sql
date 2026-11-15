/* =====================================================================================================
   PostgreSQL - second source of the model: the FTS extract (European Dynamics rows)
   Design: the FTS data live in PostgreSQL (schema fts), Power BI connects to it with PostgreSQL.Database
   (see powerquery/FtsStaging.pq, first Source line). In this repository no PostgreSQL server was installed
   on the build machine, so the report reads the same extract as CSV (fallback, stated in the README).
   Usage (psql):  \i sql/postgres/01_fts.sql     then the \copy line below from the repository root
   ===================================================================================================== */
CREATE SCHEMA IF NOT EXISTS fts;

DROP TABLE IF EXISTS fts.fts_ed;
CREATE TABLE fts.fts_ed (
    year                  SMALLINT      NOT NULL,
    beneficiary_name      TEXT          NOT NULL,
    beneficiary_country   TEXT,
    contracted_eur        NUMERIC(18,2),
    est_contracted_eur    NUMERIC(18,2),
    est_consumed_eur      NUMERIC(18,2),
    commitment_total_eur  NUMERIC(18,2),
    expense_type          TEXT,
    subject               TEXT,
    department            TEXT,
    budget_line_name      TEXT,
    programme_name        TEXT,
    beneficiary_type      TEXT,
    contract_type         TEXT,
    management_type       TEXT,
    legal_commitment_ref  TEXT,
    budget_ref            TEXT
);

-- column order must match data/processed/staging/fts_ed.csv (header row)
-- \copy fts.fts_ed (year, beneficiary_name, beneficiary_country, contracted_eur, est_contracted_eur, est_consumed_eur, commitment_total_eur, expense_type, subject, department, budget_line_name, programme_name, beneficiary_type, contract_type, management_type, legal_commitment_ref, budget_ref) FROM 'data/processed/staging/fts_ed.csv' WITH (FORMAT csv, HEADER true, ENCODING 'UTF8')

-- B-tree index for the year filter used by the report and for incremental refresh by year
CREATE INDEX IF NOT EXISTS ix_fts_ed_year ON fts.fts_ed (year);

-- Same clean-up as Power Query, in SQL (PostgreSQL dialect): former-department prefix, "CODE - Name" split
CREATE OR REPLACE VIEW fts.v_fts_clean AS
SELECT year,
       beneficiary_name,
       split_part(upper(beneficiary_name), '*', 1)                                        AS beneficiary_clean,
       regexp_replace(coalesce(nullif(department, ''), 'N/A - Not stated'), '^X - ', '')    AS department,
       split_part(regexp_replace(coalesce(nullif(department, ''), 'N/A - Not stated'), '^X - ', ''), ' - ', 1) AS department_code,
       coalesce(nullif(programme_name, ''), 'Not stated')                                  AS programme_name,
       contract_type, expense_type, contracted_eur, est_consumed_eur
FROM fts.fts_ed
WHERE year BETWEEN 2016 AND 2026;

-- Check: yearly totals (compare with qa check QA03 in SQL Server)
-- SELECT year, sum(contracted_eur) FROM fts.v_fts_clean GROUP BY year ORDER BY year;
