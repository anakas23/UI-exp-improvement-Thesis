"""
ML analiza - trenira logističku regresiju koja predviđa konverziju
(klik na "Yes, I'm interested") na temelju bihevioralnih značajki sesije.

Pokretanje:
    python3 ml_analysis.py

Rezultat: ispis metrika i koeficijenata u terminalu, + session_features.csv
"""

import sqlite3

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, confusion_matrix, roc_auc_score
from sklearn.model_selection import cross_val_score, train_test_split
from sklearn.preprocessing import StandardScaler

DB_PATH = "productivemind.db"
EXCLUDE_TIMEOUTS = True
MIN_SESSIONS_FOR_ML = 30  # ispod ovoga model nema dovoljno podataka da bude smislen


def build_session_features():
    conn = sqlite3.connect(DB_PATH)

    query = """
        SELECT
            s.session_id,
            s.variant,
            s.converted,
            s.ended_by,
            (s.end_time - s.start_time) / 1000.0 AS time_to_decision,
            MAX(CASE WHEN e.event_type = 'scroll' THEN e.scroll_percent END) AS scroll_depth,
            SUM(CASE WHEN e.event_type = 'click' THEN 1 ELSE 0 END) AS num_clicks,
            SUM(CASE WHEN e.event_type = 'mousemove' THEN 1 ELSE 0 END) AS mouse_activity_count,
            AVG(CASE WHEN e.event_type = 'mousemove' THEN e.y_percent END) AS avg_hover_y
        FROM sessions s
        LEFT JOIN events e ON s.session_id = e.session_id
        WHERE s.converted IS NOT NULL
        GROUP BY s.session_id
    """
    df = pd.read_sql(query, conn)
    conn.close()

    if EXCLUDE_TIMEOUTS:
        df = df[df["ended_by"] != "timeout"]

    # popuni nedostajuće vrijednosti (npr. sesija bez scrolla ako je sve stalo na ekran)
    df["scroll_depth"] = df["scroll_depth"].fillna(0)
    df["avg_hover_y"] = df["avg_hover_y"].fillna(0)
    df["mouse_activity_count"] = df["mouse_activity_count"].fillna(0)

    df["variant_encoded"] = df["variant"].map({"A": 0, "B": 1})

    return df


def main():
    df = build_session_features()
    df.to_csv("session_features.csv", index=False)
    print(f"Ukupno sesija (nakon filtriranja): {len(df)}")
    print("Spremljeno: session_features.csv\n")

    if len(df) < MIN_SESSIONS_FOR_ML:
        print(
            f"Imaš {len(df)} sesija, preporučeni minimum je {MIN_SESSIONS_FOR_ML}. "
            "Model je i dalje moguće trenirati ispod te granice, ali rezultate "
            "treba tumačiti isključivo ilustrativno - s ovako malim uzorkom "
            "nema statističke snage za pouzdanu generalizaciju."
        )
        if len(df) < 10:
            print("Premalo podataka za bilo kakav smislen model - prekidam.")
            return
        print()

    if df["converted"].nunique() < 2:
        print(
            "Sve sesije imaju isti ishod (sve konvertirane ili sve ne) - "
            "model nema što učiti dok ne budeš imati primjere oba ishoda."
        )
        return

    feature_cols = [
        "variant_encoded",
        "time_to_decision",
        "scroll_depth",
        "num_clicks",
        "mouse_activity_count",
        "avg_hover_y",
    ]
    X = df[feature_cols]
    y = df["converted"]

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.25, random_state=42, stratify=y
    )

    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    model = LogisticRegression()
    model.fit(X_train_scaled, y_train)

    y_pred = model.predict(X_test_scaled)

    print("=== Classification report (test set) ===")
    print(classification_report(y_test, y_pred, zero_division=0))

    print("=== Confusion matrix ===")
    print(confusion_matrix(y_test, y_pred))
    print()

    if y_test.nunique() == 2:
        y_proba = model.predict_proba(X_test_scaled)[:, 1]
        print(f"ROC-AUC (test set): {roc_auc_score(y_test, y_proba):.3f}\n")

    # 5-fold cross-validation - robusnija procjena kod malog uzorka
    if len(df) >= 5 * 2:  # barem 2 primjera po foldu u prosjeku
        try:
            X_scaled_full = StandardScaler().fit_transform(X)
            cv_scores = cross_val_score(
                LogisticRegression(), X_scaled_full, y, cv=5, scoring="roc_auc"
            )
            print(f"ROC-AUC (5-fold CV): {cv_scores.mean():.3f} ± {cv_scores.std():.3f}\n")
        except ValueError as e:
            print(f"Cross-validation preskočena: {e}\n")

    print("=== Koeficijenti (standardizirane značajke) ===")
    for feature, coef in zip(feature_cols, model.coef_[0]):
        if abs(coef) < 0.01:
            direction = "gotovo bez utjecaja"
        elif coef > 0:
            direction = "povećava"
        else:
            direction = "smanjuje"
        print(f"  {feature:24s} {coef:+.3f}  ({direction} vjerojatnost konverzije)")

    print(
        "\nNapomena: kod malog broja sesija koeficijente i metrike tumači "
        "ilustrativno - kao smjer utjecaja, ne kao statistički potvrđen "
        "generalizirajući zaključak."
    )


if __name__ == "__main__":
    main()