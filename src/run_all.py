"""Rebuild everything from the processed extracts (no download needed).

Order: SIMULATED service desk -> SQL Server warehouse (sql/01-06) -> ML model -> index test ->
Power Query files -> semantic model (TMDL) -> report pages (PBIR) -> docs -> notebook -> PDF.
Downloads and filtering are separate (python src/download_ted.py, src/download_fts.py, src/build_dataset.py,
which also writes the CPV / country reference extracts).
Usage:  python src/run_all.py
"""
import subprocess
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent
STEPS = ["simulate_service_desk.py", "load_sql.py", "ml_single_offer.py", "perf_sql.py",
         "write_powerquery.py", "build_tmdl.py", "build_report_pages.py", "build_docs.py", "build_notebook.py",
         "build_report.py"]

if __name__ == "__main__":
    for step in STEPS:
        print(f"== {step}", flush=True)
        subprocess.run([sys.executable, str(SRC / step)], check=True)
    print("all steps done")
