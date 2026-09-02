"""
ML analiza - trenira logističku regresiju koja predviđa konverziju
(klik na "Yes, I'm interested") na temelju bihevioralnih značajki sesije.

Pokretanje:
    python3 ml_analysis.py

Rezultat: ispis metrika i koeficijenata u terminalu + session_features.csv

ISPRAVLJENA VERZIJA:
  1. Značajke se računaju isključivo iz događaja zabilježenih PRIJE odluke
     (učitavanje preko session_data.py). U staroj verziji značajke
     mouse_activity_count, avg_hover_y i num_clicks uključivale su i
     ponašanje zabilježeno nakon klika, dakle nakon ishoda koji se predviđa.
     To je oblik curenja podataka i glavni razlog zašto je model postizao
     ROC-AUC ispod razine slučajnog pogađanja.
  2. Standardizacija je premještena u cjevovod (Pipeline) unutar unakrsne
     provjere valjanosti. Stara verzija standardizirala je cijeli skup prije
     podjele, čime su podaci iz testnih preklopa utjecali na obradu podataka
     za treniranje.
  3. Značajke bez varijance automatski se izbacuju uz upozorenje. U ovom
     skupu takva je scroll_depth: gumbi su na dnu stranice, pa je svaki
     ispitanik koji je donio odluku nužno došao do dna i vrijednost je
     praktički konstantna.
  4. Uz osnovni model računa se i inačica s class_weight="balanced", kao
     provjera koliko je predviđanje većinskog razreda posljedica
     neuravnoteženosti skupa.
  5. Nedostajuća prosječna pozicija miša popunjava se medijanom, a ne nulom
     (nula bi značila sam vrh stranice, što je izmišljen podatak).
"""

import numpy as np
import pandas as pd
from sklearn.dummy import DummyClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, confusion_matrix, roc_auc_score
from sklearn.model_selection import (RepeatedStratifiedKFold, cross_val_score,
                                     permutation_test_score, train_test_split)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

import session_data

DB_PATH = "productivemind.db"
MIN_SESSIONS_FOR_ML = 30
RANDOM_STATE = 42

FEATURES = [
    "variant_encoded",
    "time_to_decision",
    "scroll_depth",
    "num_clicks",
    "mouse_activity_count",
    "avg_hover_y",
]


def make_model(balanced=False):
    return Pipeline([
        ("scaler", StandardScaler()),
        ("clf", LogisticRegression(
            max_iter=1000,
            class_weight="balanced" if balanced else None,
        )),
    ])


def main():
    df = session_data.session_features(DB_PATH)
    df.to_csv("session_features.csv", index=False)
    print(f"Ukupno sesija s donesenom odlukom: {len(df)}")
    print("Spremljeno: session_features.csv\n")

    n_pos = int(df["converted"].sum())
    n_neg = len(df) - n_pos
    print(f"Konvertirano: {n_pos} ({n_pos/len(df)*100:.1f} %), "
          f"nije konvertirano: {n_neg} ({n_neg/len(df)*100:.1f} %)")
    print(f"Većinski razred kao osnovna razina točnosti: "
          f"{max(n_pos, n_neg)/len(df)*100:.1f} %\n")

    if df["converted"].nunique() < 2:
        print("Sve sesije imaju isti ishod - model nema što učiti.")
        return
    if len(df) < 10:
        print("Premalo podataka za bilo kakav smislen model - prekidam.")
        return

    # Broj primjera manjinskog razreda po značajki (engl. events per variable).
    # Uobičajena preporuka je barem 10; ispod toga su procjene koeficijenata
    # nestabilne bez obzira na to koliko je model jednostavan.
    epv = min(n_pos, n_neg) / len(FEATURES)
    if len(df) < MIN_SESSIONS_FOR_ML or epv < 10:
        print(f"UPOZORENJE: {min(n_pos, n_neg)} primjera manjinskog razreda na "
              f"{len(FEATURES)} značajki = {epv:.1f} po značajki (preporuka: >= 10). "
              "Rezultate treba tumačiti isključivo ilustrativno.\n")

    # Značajke bez varijance ne nose informaciju i samo troše stupnjeve slobode.
    used = []
    for f in FEATURES:
        if df[f].nunique() <= 1 or df[f].std() < 1e-9:
            print(f"Izbačena značajka bez varijance: {f} "
                  f"(sve sesije imaju vrijednost {df[f].iloc[0]})")
        elif (df[f].value_counts(normalize=True).iloc[0] > 0.95):
            print(f"Izbačena gotovo konstantna značajka: {f} "
                  f"({df[f].value_counts(normalize=True).iloc[0]*100:.0f} % "
                  "sesija ima istu vrijednost)")
        else:
            used.append(f)
    if len(used) < len(FEATURES):
        print()

    X = df[used]
    y = df["converted"]

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.25, random_state=RANDOM_STATE, stratify=y
    )

    model = make_model()
    model.fit(X_train, y_train)
    y_pred = model.predict(X_test)

    print("=== Classification report (test set) ===")
    print(classification_report(y_test, y_pred, zero_division=0))

    print("=== Confusion matrix ===")
    print(confusion_matrix(y_test, y_pred))
    print()

    if y_test.nunique() == 2:
        y_proba = model.predict_proba(X_test)[:, 1]
        auc = roc_auc_score(y_test, y_proba)
        n_pairs = int((y_test == 0).sum() * (y_test == 1).sum())
        print(f"ROC-AUC (test set): {auc:.3f}")
        print(f"  Napomena: testni skup ima {int((y_test==0).sum())} negativnih i "
              f"{int((y_test==1).sum())} pozitivnih primjera, pa ROC-AUC može "
              f"poprimiti samo {n_pairs + 1} različitih vrijednosti; jedan par "
              f"mijenja rezultat za {1/n_pairs:.3f}.\n")

    # Unakrsna provjera valjanosti - standardizacija je unutar cjevovoda, pa se
    # računa iznova u svakom preklopu i podaci iz testnog preklopa ne cure.
    # 5 preklopa ponovljenih 10 puta - kod 35 sesija jedna podjela daje
    # procjenu s prevelikim rasponom, pa se prosjek uzima preko 50 procjena.
    cv = RepeatedStratifiedKFold(n_splits=5, n_repeats=10, random_state=RANDOM_STATE)
    for label, mdl in (("osnovni model", make_model()),
                       ("class_weight='balanced'", make_model(balanced=True))):
        scores = cross_val_score(mdl, X, y, cv=cv, scoring="roc_auc")
        print(f"ROC-AUC (CV 5x10, {label}): {scores.mean():.3f} ± {scores.std():.3f}")

    dummy = cross_val_score(
        DummyClassifier(strategy="stratified", random_state=RANDOM_STATE),
        X, y, cv=cv, scoring="roc_auc")
    print(f"ROC-AUC (CV, nasumično pogađanje): {dummy.mean():.3f} ± {dummy.std():.3f}")

    # Permutacijski test: model se trenira i na podacima s nasumično
    # ispremiješanim ishodima. Ako rezultat na stvarnim ishodima nije bolji od
    # rezultata na ispremiješanima, model nije pronašao nikakvu vezu.
    score, perm_scores, p_value = permutation_test_score(
        make_model(), X, y, scoring="roc_auc",
        cv=RepeatedStratifiedKFold(n_splits=5, n_repeats=2, random_state=RANDOM_STATE),
        n_permutations=500, random_state=RANDOM_STATE, n_jobs=-1)
    print(f"Permutacijski test: ROC-AUC = {score:.3f}, "
          f"prosjek na ispremiješanim ishodima = {perm_scores.mean():.3f}, "
          f"p = {p_value:.3f}")
    print("  → " + ("model je bolji od slučajnosti (p < 0.05)." if p_value < 0.05
                    else "model nije bolji od slučajnosti (p >= 0.05).") + "\n")

    # Koeficijenti se čitaju iz modela treniranog na cijelom skupu, jer je
    # cilj opisati smjer veze, a ne evaluirati izvedbu.
    full = make_model()
    full.fit(X, y)
    coefs = full.named_steps["clf"].coef_[0]

    print("=== Koeficijenti (standardizirane značajke, cijeli skup) ===")
    for feature, coef in zip(used, coefs):
        if abs(coef) < 0.01:
            direction = "gotovo bez utjecaja"
        elif coef > 0:
            direction = "povećava"
        else:
            direction = "smanjuje"
        print(f"  {feature:24s} {coef:+.3f}  ({direction} vjerojatnost konverzije)")

    # Stabilnost koeficijenata: ako se predznak mijenja ovisno o tome koje su
    # sesije u skupu, koeficijent se ne smije interpretirati.
    print("\n=== Stabilnost koeficijenata (200 bootstrap uzoraka) ===")
    rng = np.random.default_rng(RANDOM_STATE)
    boot = []
    for _ in range(200):
        idx = rng.choice(len(df), len(df), replace=True)
        yb = y.iloc[idx]
        if yb.nunique() < 2:
            continue
        m = make_model()
        m.fit(X.iloc[idx], yb)
        boot.append(m.named_steps["clf"].coef_[0])
    boot = np.array(boot)
    for i, feature in enumerate(used):
        share = 100 * np.mean(np.sign(boot[:, i]) == np.sign(coefs[i]))
        lo, hi = np.percentile(boot[:, i], [2.5, 97.5])
        print(f"  {feature:24s} isti predznak u {share:5.1f} % uzoraka, "
              f"95 % raspon [{lo:+.2f}, {hi:+.2f}]")

    print(
        "\nNapomena: kod ovako malog uzorka koeficijente i metrike treba tumačiti "
        "ilustrativno - kao naznaku smjera, a ne kao statistički potvrđen "
        "generalizirajući zaključak."
    )


if __name__ == "__main__":
    main()