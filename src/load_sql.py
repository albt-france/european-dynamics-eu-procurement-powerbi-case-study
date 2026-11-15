"""Build the SQL Server warehouse end to end.

  1. sql/01  database + schemas
  2. load every CSV of data/processed/staging/ into stg.<file name> (raw landing: all columns NVARCHAR)
  3. sql/02 .. sql/06 in order (reference data, star schema, T-SQL ETL, Power BI views, quality checks)
  4. export the quality-check results to data/processed/qa_checks.csv

Connection: SQL_SERVER / SQL_DATABASE in .env (defaults: (localdb)\\MSSQLLocalDB and EuroDynDW, Windows auth).
Usage:  python src/load_sql.py
"""
import os
import re
import time
from pathlib import Path

import pandas as pd
import pyodbc

ROOT = Path(__file__).resolve().parents[1]
ST = ROOT / "data" / "processed" / "staging"
SQL = ROOT / "sql"


def env(key, default):
    f = ROOT / ".env"
    if f.exists():
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith(key + "="):
                return line.split("=", 1)[1].strip()
    return os.environ.get(key, default)


SERVER = env("SQL_SERVER", r"(localdb)\MSSQLLocalDB")
DATABASE = env("SQL_DATABASE", "EuroDynDW")
DRIVERS = ["ODBC Driver 18 for SQL Server", "ODBC Driver 17 for SQL Server", "SQL Server Native Client 11.0", "SQL Server"]


def connect(database="master"):
    driver = next(d for d in DRIVERS if d in pyodbc.drivers())
    extra = ";TrustServerCertificate=yes" if "ODBC Driver 18" in driver else ""
    return pyodbc.connect(f"DRIVER={{{driver}}};SERVER={SERVER};DATABASE={database};Trusted_Connection=yes{extra}",
                          autocommit=True)


def run_script(cn, path):
    batches = re.split(r"^\s*GO\s*$", path.read_text(encoding="utf-8"), flags=re.M | re.I)
    cur = cn.cursor()
    for b in batches:
        if b.strip():
            cur.execute(b)
            while cur.nextset():
                pass
    print(f"  ran {path.name} ({len(batches)} batches)")


def load_staging(cn):
    cur = cn.cursor()
    cur.fast_executemany = True
    for f in sorted(ST.glob("*.csv")):
        table = f.stem
        d = pd.read_csv(f, dtype=str, keep_default_na=False)
        cols = ", ".join(f"[{c}] NVARCHAR(4000) NULL" for c in d.columns)
        cur.execute(f"DROP TABLE IF EXISTS stg.[{table}]; CREATE TABLE stg.[{table}] ({cols});")
        rows = [[(v[:4000] if v != "" else None) for v in r] for r in d.itertuples(index=False, name=None)]
        if rows:
            ph = ", ".join("?" * len(d.columns))
            cur.executemany(f"INSERT stg.[{table}] VALUES ({ph})", rows)
        print(f"  stg.{table}: {len(rows):,} rows")


def main():
    t0 = time.time()
    cn = connect("master")
    run_script(cn, SQL / "01_create_database_and_schemas.sql")
    cn = connect(DATABASE)
    load_staging(cn)
    for name in ["02_reference_data.sql", "03_dwh_tables.sql", "04_etl_load_dwh.sql", "05_views_powerbi.sql",
                 "06_quality_checks.sql"]:
        run_script(cn, SQL / name)
    qa = pd.read_sql("SELECT * FROM qa.CheckResult ORDER BY CheckId", cn)
    qa.to_csv(ROOT / "data" / "processed" / "qa_checks.csv", index=False)
    print(qa[["CheckId", "Status"]].value_counts("Status").to_string())
    print(f"done in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
