"""
ML_model.py
-----------
Step 4 of the JalDrishti MVP pipeline.

Trains a Random Forest to predict groundwater contamination risk (0/1/2)
near hypothetical Uranium ISR sites.

Pipeline:
  load CSV -> preprocess (impute + one-hot season) -> stratified split
  -> RandomForestClassifier -> metrics -> feature importance -> save .joblib
"""

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import (classification_report, confusion_matrix,
                             accuracy_score, f1_score)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

HERE = Path(__file__).parent
DATA = HERE / "synthetic_isr_dataset.csv"
OUT_MODEL = HERE / "isr_risk_model.joblib"
OUT_METRICS = HERE / "model_metrics.json"

CLASS_NAMES = {0: "Low", 1: "Medium", 2: "High"}

NUMERIC = ["latitude", "longitude", "distance_from_isr", "groundwater_depth",
           "pH", "EC", "TDS", "sulfate", "nitrate", "chloride",
           "iron", "manganese", "arsenic",
           "rainfall", "hydraulic_conductivity", "porosity"]
CATEGORICAL = ["season"]


def build_pipeline():
    pre = ColumnTransformer([
        ("num", SimpleImputer(strategy="median"), NUMERIC),
        ("cat", OneHotEncoder(handle_unknown="ignore"), CATEGORICAL),
    ])
    rf = RandomForestClassifier(
        n_estimators=300,
        max_depth=None,
        min_samples_leaf=2,
        class_weight="balanced",
        n_jobs=-1,
        random_state=42,
    )
    return Pipeline([("preprocess", pre), ("rf", rf)])


def main():
    print(f"Loading dataset: {DATA}")
    df = pd.read_csv(DATA)
    print(f"  rows={len(df)}  cols={df.shape[1]}")
    print("  class counts:")
    print(df["risk_level"].value_counts().sort_index()
          .rename(CLASS_NAMES).to_string())

    X = df[NUMERIC + CATEGORICAL]
    y = df["risk_level"]

    X_tr, X_te, y_tr, y_te = train_test_split(
        X, y, test_size=0.20, stratify=y, random_state=42)
    print(f"\nTrain rows: {len(X_tr)}   Test rows: {len(X_te)}")

    pipe = build_pipeline()
    print("\nTraining RandomForest…")
    pipe.fit(X_tr, y_tr)

    y_pred = pipe.predict(X_te)
    acc = accuracy_score(y_te, y_pred)
    f1 = f1_score(y_te, y_pred, average="macro")
    print(f"\nAccuracy : {acc:.4f}")
    print(f"Macro F1 : {f1:.4f}")

    print("\nPer-class report:")
    print(classification_report(y_te, y_pred,
          target_names=[CLASS_NAMES[i] for i in sorted(CLASS_NAMES)]))

    print("Confusion matrix (rows=true, cols=pred):")
    cm = confusion_matrix(y_te, y_pred)
    print("        Low   Med  High")
    for i, row in enumerate(cm):
        print(f" {CLASS_NAMES[i]:>4} | " + "  ".join(f"{v:4d}" for v in row))

    # Feature importance (numeric features only — categorical season is small)
    rf = pipe.named_steps["rf"]
    feat_names = NUMERIC + list(
        pipe.named_steps["preprocess"]
            .named_transformers_["cat"]
            .get_feature_names_out(CATEGORICAL))
    importances = sorted(zip(feat_names, rf.feature_importances_),
                         key=lambda t: t[1], reverse=True)

    print("\nFeature importances (top 12):")
    for name, val in importances[:12]:
        bar = "#" * int(val * 200)
        print(f"  {name:<30} {val:.4f}  {bar}")

    # Save
    joblib.dump(pipe, OUT_MODEL)
    print(f"\nModel saved -> {OUT_MODEL}")

    metrics = {
        "accuracy": acc,
        "macro_f1": f1,
        "confusion_matrix": cm.tolist(),
        "feature_importances": [{"feature": n, "importance": float(v)}
                                for n, v in importances],
        "n_train": len(X_tr),
        "n_test": len(X_te),
    }
    OUT_METRICS.write_text(json.dumps(metrics, indent=2))
    print(f"Metrics saved -> {OUT_METRICS}")

    # Tiny prediction demo
    print("\n--- Demo predictions on 5 test rows ---")
    demo = X_te.head(5).copy()
    demo["true"] = y_te.head(5).map(CLASS_NAMES).values
    demo["pred"] = pd.Series(y_pred[:5]).map(CLASS_NAMES).values
    print(demo[["distance_from_isr", "TDS", "sulfate", "arsenic",
                "true", "pred"]].to_string(index=False))


if __name__ == "__main__":
    main()
