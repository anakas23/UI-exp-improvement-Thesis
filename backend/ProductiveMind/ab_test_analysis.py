"""
A/B analiza konverzija - usporedba stope konverzije između varijante A i B,
uz chi-kvadrat test statističke značajnosti.

Pokretanje:
    python3 ab_test_analysis.py

Rezultat: ispis u terminalu + ab_conversion_comparison.png
"""

import sqlite3

import matplotlib.pyplot as plt
import pandas as pd
from scipy.stats import chi2_contingency, fisher_exact

DB_PATH = "productivemind.db"

# Ako je True, sesije zatvorene safety-timeoutom (ne eksplicitnom odlukom
# korisnika) se izbacuju iz analize - preporučeno, jer timeout ne
# predstavlja stvarnu odluku "da/ne".
EXCLUDE_TIMEOUTS = True


def load_sessions():
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql(
        "SELECT variant, converted, ended_by FROM sessions WHERE converted IS NOT NULL",
        conn,
    )
    conn.close()
    return df


def main():
    df = load_sessions()

    if EXCLUDE_TIMEOUTS:
        n_timeouts = (df["ended_by"] == "timeout").sum()
        df = df[df["ended_by"] != "timeout"]
        if n_timeouts:
            print(f"Izbačeno {n_timeouts} sesija zatvorenih safety-timeoutom.\n")

    if len(df) == 0:
        print("Nema podataka u bazi - pokreni prikupljanje prije analize.")
        return

    summary = df.groupby("variant").agg(
        total_sessions=("converted", "size"),
        conversions=("converted", "sum"),
    )
    summary["conversion_rate"] = summary["conversions"] / summary["total_sessions"]

    print("=== Pregled po varijanti ===")
    print(summary)
    print()

    if len(summary) < 2:
        print(
            "Imaš podatke samo za jednu varijantu - potrebno je barem "
            "nekoliko sesija za obje varijante (A i B) da se može uspoređivati."
        )
        return

    if (summary["total_sessions"] < 15).any():
        print(
            "UPOZORENJE: manje od 15 sesija za barem jednu varijantu. "
            "Rezultat testa niže treba tumačiti oprezno/ilustrativno - "
            "s ovako malim uzorkom test vjerojatno nema dovoljno statističke "
            "snage da pouzdano detektira razliku, čak i ako razlika stvarno postoji.\n"
        )

    # kontingencijska tablica: [konverzije, ne-konverzije] za svaku varijantu
    contingency = [
        [row["conversions"], row["total_sessions"] - row["conversions"]]
        for _, row in summary.iterrows()
    ]

    chi2, p_value, dof, expected = chi2_contingency(contingency)

    print("=== Chi-kvadrat test ===")
    print(f"chi2 = {chi2:.3f}, p-vrijednost = {p_value:.4f}")
    if p_value < 0.05:
        print("→ Statistički značajna razlika između varijanti (p < 0.05).")
    else:
        print(
            "→ Nema statistički značajne razlike (p >= 0.05) - razlika "
            "u konverziji koju vidiš mogla je nastati slučajno."
        )

    # chi-kvadrat pretpostavlja da je očekivani broj u svakoj ćeliji tablice
    # barem ~5 - kod malih uzoraka (kao ovdje) ta pretpostavka lako ne vrijedi,
    # pa je rezultat chi-kvadrat testa u tom slučaju nepouzdan.
    min_expected = expected.min()
    chi2_reliable = min_expected >= 5
    if not chi2_reliable:
        print(
            f"\nNapomena: najmanja očekivana vrijednost u tablici je {min_expected:.2f} "
            "(< 5) - chi-kvadrat pretpostavka nije zadovoljena kod ovako malog "
            "uzorka, pa je chi-kvadrat rezultat iznad manje pouzdan. Fisherov "
            "egzaktni test niže je ispravniji izbor za ovu veličinu uzorka."
        )
    print()

    # Fisherov egzaktni test - preciznija alternativa chi-kvadratu kod malih
    # uzoraka, jer ne oslanja na aproksimaciju nego računa točnu vjerojatnost.
    # Radi samo za 2x2 tablice (dvije varijante, dva ishoda - baš tvoj slučaj).
    print("=== Fisherov egzaktni test ===")
    if len(contingency) == 2 and len(contingency[0]) == 2:
        odds_ratio, p_value_fisher = fisher_exact(contingency)
        print(f"odds ratio = {odds_ratio:.3f}, p-vrijednost = {p_value_fisher:.4f}")
        if p_value_fisher < 0.05:
            print("→ Statistički značajna razlika između varijanti (p < 0.05).")
        else:
            print(
                "→ Nema statistički značajne razlike (p >= 0.05) - razlika "
                "u konverziji koju vidiš mogla je nastati slučajno."
            )
        print(
            "\nPreporuka: kod ovako malog uzorka navedi u radu Fisherov "
            "rezultat kao primarni, a chi-kvadrat spomeni kao dodatnu "
            "(manje pouzdanu) potvrdu."
        )
    else:
        p_value_fisher = None
        print("Fisherov test radi samo za 2x2 tablicu (dvije varijante) - preskočeno.")
    print()

    # bar chart usporedbe
    fig, ax = plt.subplots(figsize=(5, 4))
    ax.bar(summary.index, summary["conversion_rate"], color=["#4FA3F7", "#6E8C77"])
    for i, (idx, row) in enumerate(summary.iterrows()):
        ax.text(
            i,
            row["conversion_rate"] + 0.01,
            f"{row['conversion_rate']*100:.1f}%\n(n={int(row['total_sessions'])})",
            ha="center",
            fontsize=10,
        )
    ax.set_ylim(0, max(summary["conversion_rate"]) + 0.15)
    ax.set_ylabel("Stopa konverzije")
    title_p = p_value_fisher if p_value_fisher is not None else p_value
    ax.set_title(f"Konverzija po varijanti (Fisher p={title_p:.3f})")
    fig.tight_layout()
    fig.savefig("ab_conversion_comparison.png", dpi=150)
    plt.close(fig)
    print("Graf spremljen: ab_conversion_comparison.png")


if __name__ == "__main__":
    main()