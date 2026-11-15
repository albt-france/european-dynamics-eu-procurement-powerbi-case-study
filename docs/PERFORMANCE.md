# Performance: what was measured, what was changed

Two layers: the **warehouse** (what Power Query and DirectQuery would send to SQL Server) and the **semantic model**
(what the report's visuals query). Numbers below come from `src/perf_sql.py` (`data/processed/perf_sql.csv`).

## 1. SQL Server: indexes, before / after (measured)

Three queries shaped like the report's visuals, warm cache, logical reads from `SET STATISTICS IO`, median of 15 runs.

| Query (report use) | No nonclustered index | First index set | Tuned covering indexes |
|---|---|---|---|
| Awards and value per year, one entity (Overview) | 190 reads, 2.4 ms | 10 reads, 0.3 ms | **6 reads, 0.4 ms** |
| Awards for one buyer (tooltip / drill-through) | 372 reads, 3.5 ms | 216 reads, 2.5 ms | **6 reads, 0.4 ms** |
| One month of awards (date slicer) | 186 reads, 0.5 ms | 122 reads, 0.3 ms | **3 reads, 0.2 ms** |

What changed between the first and the tuned set (a real mistake, kept here because the fix is the lesson): the first
indexes `INCLUDE`d `ValueEUR`, but the measures had moved to `ValueSplitEUR`, so every seek still needed a key
lookup into the clustered index. Including the column actually summed, plus an `(IsED, BuyerKey)` index for the
"ED rows by buyer" ranking, makes the three queries covering seeks: logical reads divided by 30 to 120.
At this data size (6,000 award rows) milliseconds do not matter; the reads show how the same design scales.

## 2. Semantic model: design choices (applied)

| Choice | Why it helps |
|---|---|
| Star schema, integer surrogate keys, one-to-many, **single-direction** relationships | small dictionaries, cheap joins, no ambiguous filter paths |
| **Narrow views** (`pbi.*`): FactAward imports 21 of 24 warehouse columns, technical columns stay in SQL | fewer columns = smaller model, faster refresh |
| `CountedValueEUR` / `ValueSplitEUR` **pre-computed in SQL** | measures are plain `SUM`s, no row-by-row `FILTER` in DAX |
| **Auto date/time off** (`__PBI_TimeIntelligenceEnabled = 0`) + one marked date table | no hidden date table per date column |
| `discourageImplicitMeasures` + explicit measures in one table | predictable queries, required by the calculation group |
| Calculation group for time variants | 6 items instead of 6 x N measures to maintain |
| High-cardinality text (`Title`, notice URL) only in a detail table, never on an axis | keeps visual queries on low-cardinality columns |
| Query folding on every SQL source (checked with *View Native Query*) | the database does the filtering; enables incremental refresh |
| Import mode | data change daily at most; DirectQuery is kept as an option because the views and indexes support it |

## 3. Performance Analyzer (Power BI Desktop) - procedure

To run in Power BI Desktop (View > Performance analyzer > Start recording > Refresh visuals), per page:

1. record the **DAX query** and **visual display** time of each visual; copy the slowest query to DAX Studio
   (optional, free) and check *Server timings* (storage engine vs formula engine) and VertiPaq Analyzer (column sizes);
2. targets: every visual under 500 ms, page under 2 s on a laptop;
3. typical fixes if a visual is slow: replace an iterator over the fact table by a pre-computed column in SQL,
   reduce visuals per page (each visual = at least one query), avoid bidirectional filters, remove unused columns.

Screenshots (before / after) go to `docs/img/perf_*.png` once taken in Desktop; this repository was built without
Desktop screen access, so the Desktop timings are not reported here rather than estimated.
