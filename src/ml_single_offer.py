"""Small, explained ML model: can public notice features predict that an IT-services lot gets a single offer?

Data: dwh.FactAward rows in CPV division 72 with a published number of offers (legacy + eForms, all suppliers).
Target: NumberOfOffers = 1. Features (all public, known when the award is published):
  procedure family, framework agreement, buyer type, buyer country, CPV group (3 digits), log10(value), year,
  TED format (legacy / eForms).
Models: logistic regression (interpretable baseline) and gradient boosting; 5-fold stratified cross-validation,
ROC AUC and average precision; permutation importance on a held-out split.
Limits (also in the report): small sample, buyers and years are not independent, "single offer" is not an anomaly
in itself, and correlation is not cause. The model describes patterns; it does not judge any procurement.

Writes data/processed/ml_metrics.json and data/processed/ml_feature_importance.csv
Usage:  python src/ml_single_offer.py
"""
import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import pyodbc
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold, cross_validate, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "processed"
QUERY = """
SELECT p.ProcedureFamily AS procedure_family, CAST(f.IsFramework AS INT) AS framework, b.BuyerType AS buyer_type,
       ISNULL(c.ISO3, 'UNK') AS buyer_country, LEFT(cpv.CpvCode, 3) AS cpv_group,
       LOG10(NULLIF(COALESCE(f.ValueSplitEUR, f.ValueEUR), 0)) AS log_value, d.[Year] AS [year], d.TedFormat AS ted_format,
       CAST(f.IsED AS INT) AS is_ed, IIF(f.NumberOfOffers = 1, 1, 0) AS single_offer
FROM dwh.FactAward f
JOIN dwh.DimDate d ON d.DateKey = f.DateKey
JOIN dwh.DimCPV cpv ON cpv.CpvKey = f.CpvKey
JOIN dwh.DimProcedure p ON p.ProcedureKey = f.ProcedureKey
JOIN dwh.DimBuyer b ON b.BuyerKey = f.BuyerKey
LEFT JOIN dwh.DimCountry c ON c.CountryKey = f.CountryKey
WHERE cpv.IsITServices = 1 AND f.NumberOfOffers IS NOT NULL AND f.NumberOfOffers > 0
"""
CAT = ["procedure_family", "buyer_type", "buyer_country", "cpv_group", "ted_format"]
NUM = ["framework", "log_value", "year"]
LABELS = {"procedure_family": "Procedure", "buyer_type": "Buyer type", "buyer_country": "Buyer country",
          "cpv_group": "CPV group", "ted_format": "TED format", "framework": "Framework agreement",
          "log_value": "Contract value (log)", "year": "Year"}


def load():
    from load_sql import connect, DATABASE
    cn = connect(DATABASE)
    return pd.read_sql(QUERY, cn)


def pipeline(model):
    pre = ColumnTransformer([
        ("cat", Pipeline([("imp", SimpleImputer(strategy="constant", fill_value="missing")),
                          ("oh", OneHotEncoder(handle_unknown="ignore", min_frequency=20, sparse_output=False))]), CAT),
        ("num", Pipeline([("imp", SimpleImputer(strategy="median")), ("sc", StandardScaler())]), NUM)])
    return Pipeline([("pre", pre), ("model", model)])


def main():
    df = load()
    X, y = df[CAT + NUM], df.single_offer
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    models = {"Logistic regression": LogisticRegression(max_iter=2000, class_weight="balanced"),
              "Gradient boosting": HistGradientBoostingClassifier(max_depth=3, learning_rate=0.08, max_iter=200,
                                                                  random_state=42)}
    metrics = {"rows": int(len(df)), "single_offer_rate": float(y.mean()), "models": {}}
    for name, m in models.items():
        s = cross_validate(pipeline(m), X, y, cv=cv, scoring=["roc_auc", "average_precision"])
        metrics["models"][name] = {"roc_auc": float(np.mean(s["test_roc_auc"])),
                                   "roc_auc_sd": float(np.std(s["test_roc_auc"])),
                                   "avg_precision": float(np.mean(s["test_average_precision"]))}
    best = max(metrics["models"], key=lambda k: metrics["models"][k]["roc_auc"])
    metrics["best_model"] = best
    Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.25, stratify=y, random_state=42)
    fitted = pipeline(models[best]).fit(Xtr, ytr)
    imp = permutation_importance(fitted, Xte, yte, scoring="roc_auc", n_repeats=20, random_state=42)
    fi = pd.DataFrame({"feature": [LABELS[c] for c in X.columns], "importance": imp.importances_mean,
                       "importance_sd": imp.importances_std}).sort_values("importance", ascending=False)
    fi["rank"] = range(1, len(fi) + 1)
    # single-offer rate by procedure family (descriptive, for the report)
    rates = df.groupby("procedure_family").single_offer.agg(["mean", "size"]).reset_index()
    metrics["rate_by_procedure"] = {r.procedure_family: {"rate": float(r["mean"]), "n": int(r["size"])}
                                    for _, r in rates.iterrows()}
    metrics["ed_single_offer_rate"] = float(df.loc[df.is_ed == 1, "single_offer"].mean())
    metrics["ed_rows"] = int((df.is_ed == 1).sum())
    (OUT / "ml_metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    fi.to_csv(OUT / "ml_feature_importance.csv", index=False)
    print(json.dumps({k: v for k, v in metrics.items() if k != "rate_by_procedure"}, indent=1))
    print(fi.to_string(index=False))


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    main()
