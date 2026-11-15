"""SIMULATED data for the e-Government service desk page (fictional ministry, fictional agencies).

Nothing here is linked to European Dynamics, its clients or its contracts. The page exists to demonstrate
SLA measures and row-level security (RLS) by agency. Seeded, so every run gives the same file.
Writes data/processed/staging/sim_service_request.csv, sim_agency.csv, sim_user_agency.csv
Usage:  python src/simulate_service_desk.py
"""
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
ST = ROOT / "data" / "processed" / "staging"
rng = np.random.default_rng(42)

AGENCIES = [  # code, name, volume weight, staffing factor (higher = faster)
    ("TAX", "Tax Administration Agency", 0.30, 1.00),
    ("SOC", "Social Insurance Agency", 0.24, 0.80),
    ("REG", "Civil Registry Office", 0.16, 1.20),
    ("BUS", "Business Registry", 0.12, 1.10),
    ("LAND", "Land Registry", 0.10, 0.65),
    ("VEH", "Vehicle Licensing Authority", 0.08, 0.95),
]
SERVICES = {"TAX": ["Tax certificate", "Refund enquiry", "Payment plan"],
            "SOC": ["Benefit application", "Contribution record", "Pension enquiry"],
            "REG": ["Birth certificate", "Marriage certificate", "Address change"],
            "BUS": ["Company registration", "Registry extract", "Statute amendment"],
            "LAND": ["Title search", "Ownership transfer", "Cadastral correction"],
            "VEH": ["Licence renewal", "Vehicle registration", "Plate replacement"]}
CHANNELS, CH_P = ["Online portal", "Phone", "E-mail", "Front desk"], [0.58, 0.18, 0.14, 0.10]
PRIORITY = {"High": (24, 0.12), "Normal": (72, 0.68), "Low": (120, 0.20)}  # SLA target hours, share


def main():
    ST.mkdir(parents=True, exist_ok=True)
    n = 48_000
    days = pd.date_range("2025-01-01", "2026-10-31", freq="D")
    season = np.asarray(1 + 0.25 * np.sin((days.day_of_year - 60) / 365 * 2 * np.pi) - 0.45 * (days.day_of_week >= 5), dtype=float)
    day = rng.choice(len(days), size=n, p=season / season.sum())
    ag = rng.choice(len(AGENCIES), size=n, p=[a[2] for a in AGENCIES])
    pr_names = list(PRIORITY)
    pr = rng.choice(len(pr_names), size=n, p=[PRIORITY[p][1] for p in pr_names])
    ch = rng.choice(len(CHANNELS), size=n, p=CH_P)
    opened = days[day] + pd.to_timedelta(rng.integers(7 * 60, 19 * 60, size=n), unit="m")
    target = np.array([PRIORITY[pr_names[i]][0] for i in pr])
    speed = np.array([AGENCIES[i][3] for i in ag])
    # resolution time: log-normal around a share of the target; online requests are faster; a 2026 improvement
    improve = np.where(days[day].year == 2026, 0.85, 1.0)
    chan = np.where(ch == 0, 0.8, 1.1)
    hours = target * rng.lognormal(mean=np.log(0.55), sigma=0.6, size=n) * chan * improve / speed
    status = np.where(opened > pd.Timestamp("2026-10-31") - pd.to_timedelta(hours, unit="h"), "Open", "Closed")
    closed = np.where(status == "Closed", opened + pd.to_timedelta(hours, unit="h"), pd.NaT)
    df = pd.DataFrame({
        "request_id": [f"SR-{i:06d}" for i in range(1, n + 1)],
        "agency_code": [AGENCIES[i][0] for i in ag],
        "service": [SERVICES[AGENCIES[a][0]][rng.integers(0, 3)] for a in ag],
        "channel": [CHANNELS[i] for i in ch],
        "priority": [pr_names[i] for i in pr],
        "opened_at": opened.strftime("%Y-%m-%d %H:%M"),
        "closed_at": pd.to_datetime(closed).strftime("%Y-%m-%d %H:%M"),
        "sla_target_hours": target,
        "resolution_hours": np.where(status == "Closed", hours.round(1), np.nan),
        "status": status,
        "satisfaction": np.where(status == "Closed",
                                 np.clip(np.round(5 - hours / target * 1.6 + rng.normal(0, 0.7, n)), 1, 5), np.nan),
    }).sort_values("opened_at")
    df.to_csv(ST / "sim_service_request.csv", index=False)
    pd.DataFrame([(a[0], a[1], "Ministry of Digital Services (fictional)") for a in AGENCIES],
                 columns=["agency_code", "agency_name", "ministry"]).to_csv(ST / "sim_agency.csv", index=False)
    users = [(f"{a[0].lower()}.lead@ministry.example", a[0]) for a in AGENCIES]
    users += [("deputy.director@ministry.example", "TAX"), ("deputy.director@ministry.example", "SOC")]
    pd.DataFrame(users, columns=["user_principal_name", "agency_code"]).to_csv(ST / "sim_user_agency.csv", index=False)
    print(f"simulated requests: {len(df):,}; open {int((df.status == 'Open').sum())}")


if __name__ == "__main__":
    main()
