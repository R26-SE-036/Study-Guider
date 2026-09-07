"""Fit the cognitive-state classifier, and be honest about what it measures.

============================ WHAT CHANGED, AND WHY ============================
This trainer read `data/dataset.csv` - ten handwritten rows - split 80/20, and
printed an accuracy. Eight rows to train on, TWO to test, three classes: the
printed number could only be 0%, 50% or 100%, and it measured nothing either
way. The resulting `cognitive_model.pkl` was a threshold on `error_count` in a
pickle.

It now trains on `data/cognitive_rubric_dataset.csv`, generated from the stated
rubric in app/services/cognitive_rubric.py. That does not make the model a
discovery, and this file does not pretend otherwise:

    the metric below is FIDELITY TO THE RUBRIC.
    It says how closely the classifier reproduces a rule we wrote down.
    It is not evidence about students, and must not be reported as accuracy
    at predicting cognitive state.

That is a claim the data can actually support, which the old one was not.

The honest alternative was to delete the model and call `cognitive_rubric.classify`
directly. The model is kept for two reasons: it smooths the rubric's step
boundaries, so a student one error either side of a cut does not flip between a
beginner's explanation and a terse correction; and it is the slot real labels go
into. Rows carry `label_source`, and this trainer prefers `human` rows whenever
any exist - so a tutor annotating real remediation triggers upgrades the model
without a line of code changing.
==============================================================================
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone

import joblib
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, confusion_matrix
from sklearn.model_selection import StratifiedKFold, cross_val_score, train_test_split

from app.services.cognitive_rubric import COGNITIVE_STATES

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_DIR = os.path.join(BASE_DIR, "models")
MODEL_PATH = os.path.join(MODEL_DIR, "cognitive_model.pkl")
CARD_PATH = os.path.join(MODEL_DIR, "model_card.json")

BACKEND_DIR = os.path.dirname(os.path.dirname(BASE_DIR))
DATA_PATH = os.path.join(BACKEND_DIR, "data", "cognitive_rubric_dataset.csv")

FEATURE_COLUMNS = ["error_count", "complexity_score", "past_score"]
TARGET = "cognitive_state"

# Below this the split is not informative and the model is a lookup table. The
# old dataset had ten.
MIN_ROWS = 300


def train_and_save_model() -> bool:
    os.makedirs(MODEL_DIR, exist_ok=True)

    if not os.path.exists(DATA_PATH):
        print(f"Dataset not found at {DATA_PATH}")
        print("Run: python dev_tools/generate_rubric_dataset.py")
        return False

    dataset = pd.read_csv(DATA_PATH)

    missing = [c for c in FEATURE_COLUMNS + [TARGET] if c not in dataset.columns]
    if missing:
        print(f"Dataset is missing columns: {missing}")
        return False

    # ── Prefer human labels if any exist ──────────────────────────────────────
    # The rubric rows are scaffolding. The moment a tutor annotates real
    # triggers, those rows are the dataset and the generated ones step aside.
    label_sources = set(dataset.get("label_source", pd.Series(["unknown"])).unique())
    human_rows = (
        dataset[dataset["label_source"] == "human"]
        if "label_source" in dataset.columns
        else dataset.iloc[0:0]
    )

    if len(human_rows) >= MIN_ROWS:
        dataset = human_rows.reset_index(drop=True)
        provenance = "human"
        print(f"Training on {len(dataset)} HUMAN-labelled rows.")
    else:
        provenance = "rubric"
        if len(human_rows):
            print(
                f"Found {len(human_rows)} human-labelled rows, fewer than the "
                f"{MIN_ROWS} needed to train on them alone. Using the rubric rows; "
                "keep annotating."
            )
        print(f"Training on {len(dataset)} rows generated from the rubric.")

    unexpected = set(dataset[TARGET].unique()) - set(COGNITIVE_STATES)
    if unexpected:
        print(f"Dataset contains states the prompt does not understand: {unexpected}")
        return False

    if len(dataset) < MIN_ROWS:
        print(f"Only {len(dataset)} rows; {MIN_ROWS} needed. Refusing to train.")
        return False

    X = dataset[FEATURE_COLUMNS]
    y = dataset[TARGET]

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, stratify=y, random_state=42
    )

    model = RandomForestClassifier(
        n_estimators=200,
        max_depth=8,
        min_samples_leaf=3,
        class_weight="balanced",
        random_state=42,
    )

    # Cross-validated first, so the headline number is not one lucky split.
    cv_scores = cross_val_score(
        model, X, y, cv=StratifiedKFold(n_splits=5, shuffle=True, random_state=42),
        scoring="f1_macro",
    )

    model.fit(X_train, y_train)
    predictions = model.predict(X_test)

    report = classification_report(y_test, predictions, output_dict=True, zero_division=0)
    matrix = confusion_matrix(y_test, predictions, labels=list(COGNITIVE_STATES))

    metric_name = (
        "accuracy at predicting cognitive state"
        if provenance == "human"
        else "fidelity to the rubric"
    )

    print(f"\n--- {metric_name} ---")
    print(f"  5-fold macro F1: {cv_scores.mean():.4f} (+/- {cv_scores.std():.4f})")
    print(f"  held-out macro F1: {report['macro avg']['f1-score']:.4f}")
    print(f"  held-out accuracy: {report['accuracy']:.4f}")
    print("\nConfusion matrix (rows true, columns predicted):")
    print(f"  {'':<22}" + "".join(f"{s[:12]:>14}" for s in COGNITIVE_STATES))
    for state, row in zip(COGNITIVE_STATES, matrix):
        print(f"  {state:<22}" + "".join(f"{v:>14}" for v in row))

    print("\nFeature importance:")
    for name, importance in sorted(
        zip(FEATURE_COLUMNS, model.feature_importances_), key=lambda p: -p[1]
    ):
        print(f"  {name:<20} {importance:.4f}")

    card = {
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "label_provenance": provenance,
        "label_sources_in_file": sorted(label_sources),
        "what_the_metric_means": (
            "How closely this classifier reproduces the decision list in "
            "app/services/cognitive_rubric.py. The rubric is a stated pedagogical "
            "judgement, not an observation: nobody measured these students' "
            "cognitive load. This number is NOT accuracy at predicting cognitive "
            "state and must not be reported as such."
            if provenance == "rubric"
            else "Accuracy against tutor-annotated remediation triggers."
        ),
        "rows": int(len(dataset)),
        "features": FEATURE_COLUMNS,
        "classes": list(COGNITIVE_STATES),
        "class_balance": {k: int(v) for k, v in dataset[TARGET].value_counts().items()},
        "cv_macro_f1_mean": round(float(cv_scores.mean()), 4),
        "cv_macro_f1_std": round(float(cv_scores.std()), 4),
        "holdout_macro_f1": round(float(report["macro avg"]["f1-score"]), 4),
        "holdout_accuracy": round(float(report["accuracy"]), 4),
        "per_class": {
            state: report[state] for state in COGNITIVE_STATES if state in report
        },
        "feature_importance": {
            name: round(float(value), 4)
            for name, value in zip(FEATURE_COLUMNS, model.feature_importances_)
        },
        "used_for": (
            "Choosing the register of the generated micro-lesson, and nothing else. "
            "It does not gate content, decide mastery, or reach a transcript."
        ),
    }

    joblib.dump(
        {"model": model, "feature_columns": FEATURE_COLUMNS, "card": card}, MODEL_PATH
    )
    with open(CARD_PATH, "w", encoding="utf-8") as handle:
        json.dump(card, handle, indent=2)

    print(f"\nWrote {MODEL_PATH}")
    print(f"Wrote {CARD_PATH}")
    if provenance == "rubric":
        print(
            "\nThis model approximates a stated rubric. Report it that way -\n"
            "see model_card.json -> what_the_metric_means."
        )
    return True


if __name__ == "__main__":
    import sys

    sys.path.insert(0, BACKEND_DIR)
    raise SystemExit(0 if train_and_save_model() else 1)
