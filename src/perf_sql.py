"""Before / after measurement of the warehouse indexes on report-style queries (SQL Server side).

For each query: logical reads (SET STATISTICS IO) and elapsed time (median of 15 runs, warm cache), first with the
nonclustered indexes of dwh.FactAward disabled ("before"), then enabled ("after"). Output: data/processed/perf_sql.csv
Usage:  python src/perf_sql.py
"""
import re
import statistics
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from load_sql import connect, DATABASE  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
INDEXES = ["IX_FactAward_Date", "IX_FactAward_Buyer", "IX_FactAward_Entity", "IX_FactAward_IsED"]
QUERIES = {
    "Awards and value per year, one entity (Overview)":
        "SELECT d.[Year], COUNT(*), SUM(f.ValueSplitEUR) FROM dwh.FactAward f JOIN dwh.DimDate d ON d.DateKey = f.DateKey "
        "WHERE f.EntityKey = 2 GROUP BY d.[Year]",
    "Awards for one buyer (drill-through / tooltip)":
        "SELECT COUNT(*), SUM(ValueSplitEUR) FROM dwh.FactAward WHERE BuyerKey = (SELECT TOP 1 BuyerKey FROM dwh.FactAward "
        "WHERE IsED = 1 GROUP BY BuyerKey ORDER BY COUNT(*) DESC)",
    "One month of awards (date slicer)":
        "SELECT COUNT(*), SUM(ValueSplitEUR) FROM dwh.FactAward WHERE DateKey BETWEEN 20220101 AND 20220131",
}


def reads(messages):
    return sum(int(m) for m in re.findall(r"logical reads (\d+)", " ".join(str(x) for x in messages)))


def run(cur, sql):
    cur.execute("SET STATISTICS IO ON; " + sql)
    cur.fetchall()
    msgs = list(cur.messages)
    while cur.nextset():
        msgs += list(cur.messages)
    lr = reads(msgs)
    times = []
    for _ in range(15):
        t0 = time.perf_counter()
        cur.execute(sql)
        cur.fetchall()
        times.append((time.perf_counter() - t0) * 1000)
    return lr, statistics.median(times)


def main():
    cn = connect(DATABASE)
    cur = cn.cursor()
    rows = []
    for state, action in (("before (no nonclustered index)", "DISABLE"), ("after (indexes)", "REBUILD")):
        for ix in INDEXES:
            cur.execute(f"ALTER INDEX {ix} ON dwh.FactAward {action}")
        for name, sql in QUERIES.items():
            lr, ms = run(cur, sql)
            rows.append({"query": name, "state": state, "logical_reads": lr, "median_ms": round(ms, 2)})
    d = pd.DataFrame(rows)
    d.to_csv(ROOT / "data" / "processed" / "perf_sql.csv", index=False)
    print(d.to_string(index=False))


if __name__ == "__main__":
    main()
