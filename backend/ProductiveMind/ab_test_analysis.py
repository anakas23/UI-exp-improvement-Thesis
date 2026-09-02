"""
A/B analiza konverzija - usporedba stope konverzije između varijante A i B,
uz Fisherov egzaktni test i hi-kvadrat test.

Pokretanje:
    python3 ab_test_analysis.py

Rezultat: ispis u terminalu + ab_conversion_comparison.png

ISPRAVLJENA VERZIJA:
  - podaci se učitavaju preko session_data.py, pa je kriterij uključivanja
    sesija identičan onome u ml_analysis.py i generate_heatmap.py;
  - dodani intervali pouzdanosti za obje stope i za razliku između njih;
  - dodan izračun potrebne veličine uzorka i najmanje razlike koju je test
    uopće bio u stanju detektirati (statistička snaga);
  - hi-kvadrat se ispisuje s Yatesovom korekcijom i bez nje, jer standardna
    implementacija za 2x2 tablicu korekciju primjenjuje automatski, što na
    malom uzorku bitno mijenja rezultat.
"""

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
from scipy.stats import chi2_contingency, fisher_exact, norm

import session_data

DB_PATH = "productivemind.db"
ALPHA = 0.05


def wilson_ci(successes, total, alpha=ALPHA):
    """Wilsonov interval pouzdanosti - pouzdaniji od normalne aproksimacije
    kod malih uzoraka i kod udjela blizu 0 ili 1."""
    if total == 0:
        return (float("nan"), float("nan"))
    z = norm.ppf(1 - alpha / 2)
    p = successes / total
    denom = 1 + z**2 / total
    centre = (p + z**2 / (2 * total)) / denom
    half = z * np.sqrt(p * (1 - p) / total + z**2 / (4 * total**2)) / denom
    return (centre - half, centre + half)


def diff_ci(s1, n1, s2, n2, alpha=ALPHA):
    """Interval pouzdanosti za razliku dvaju udjela (Wald)."""
    p1, p2 = s1 / n1, s2 / n2
    z = norm.ppf(1 - alpha / 2)
    se = np.sqrt(p1 * (1 - p1) / n1 + p2 * (1 - p2) / n2)
    d = p2 - p1
    return (d - z * se, d + z * se)


def power_two_proportions(p1, p2, n_per_group, alpha=ALPHA):
    """Snaga testa za usporedbu dvaju udjela (aproksimacija arcsin transformacijom)."""
    h = abs(2 * np.arcsin(np.sqrt(p2)) - 2 * np.arcsin(np.sqrt(p1)))
    z_alpha = norm.ppf(1 - alpha / 2)
    return float(norm.cdf(h * np.sqrt(n_per_group / 2) - z_alpha))


def n_for_power(p1, p2, power=0.8, alpha=ALPHA):
    """Potreban broj sesija po varijanti za zadanu snagu."""
    h = abs(2 * np.arcsin(np.sqrt(p2)) - 2 * np.arcsin(np.sqrt(p1)))
    if h == 0:
        return float("inf")
    z_alpha = norm.ppf(1 - alpha / 2)
    z_beta = norm.ppf(power)
    return 2 * ((z_alpha + z_beta) / h) ** 2


def mde(p1, n_per_group, power=0.8, alpha=ALPHA):
    """Najmanja razlika koju test s danim uzorkom može detektirati (oba smjera)."""
    up = next((p for p in np.arange(p1 + 0.005, 1.0, 0.005)
               if power_two_proportions(p1, p, n_per_group, alpha) >= power), None)
    down = next((p for p in np.arange(p1 - 0.005, 0.0, -0.005)
                 if power_two_proportions(p1, p, n_per_group, alpha) >= power), None)
    return down, up


def main():
    df = session_data.load_sessions(DB_PATH, decided_only=True)

    if len(df) == 0:
        print("Nema sesija s donesenom odlukom - pokreni prikupljanje prije analize.")
        return

    summary = df.groupby("variant").agg(
        total_sessions=("converted", "size"),
        conversions=("converted", "sum"),
    )
    summary["conversion_rate"] = summary["conversions"] / summary["total_sessions"]

    print("=== Pregled po varijanti (samo sesije s donesenom odlukom) ===")
    for variant, row in summary.iterrows():
        n = int(row["total_sessions"])
        k = int(row["conversions"])
        lo, hi = wilson_ci(k, n)
        print(f"  {variant}: {k}/{n} = {row['conversion_rate']*100:.1f} %"
              f"   95 % CI [{lo*100:.1f} %, {hi*100:.1f} %]")
    print()

    if len(summary) < 2:
        print("Podaci postoje samo za jednu varijantu - usporedba nije moguća.")
        return

    (v1, r1), (v2, r2) = list(summary.iterrows())
    n1, k1 = int(r1["total_sessions"]), int(r1["conversions"])
    n2, k2 = int(r2["total_sessions"]), int(r2["conversions"])

    d_lo, d_hi = diff_ci(k1, n1, k2, n2)
    observed_diff = k2 / n2 - k1 / n1
    print(f"Razlika ({v2} - {v1}): {observed_diff*100:+.1f} postotnih bodova, "
          f"95 % CI [{d_lo*100:+.1f}, {d_hi*100:+.1f}]")
    print()

    contingency = [[k1, n1 - k1], [k2, n2 - k2]]

    print("=== Fisherov egzaktni test (primarni) ===")
    odds_ratio, p_fisher = fisher_exact(contingency)
    print(f"odds ratio = {odds_ratio:.3f}, p-vrijednost = {p_fisher:.4f}")
    print("→ " + ("Statistički značajna razlika (p < 0.05)."
                  if p_fisher < ALPHA else
                  "Nema statistički značajne razlike (p >= 0.05)."))
    print()

    print("=== Hi-kvadrat test (dodatna provjera) ===")
    chi2_y, p_y, _, expected = chi2_contingency(contingency)
    chi2_n, p_n, _, _ = chi2_contingency(contingency, correction=False)
    print(f"s Yatesovom korekcijom:  chi2 = {chi2_y:.3f}, p = {p_y:.4f}")
    print(f"bez korekcije:           chi2 = {chi2_n:.3f}, p = {p_n:.4f}")
    print(f"najmanja očekivana frekvencija = {expected.min():.2f}")
    if expected.min() < 5:
        print("  Pretpostavka o očekivanoj frekvenciji >= 5 nije zadovoljena, "
              "pa je Fisherov test pouzdaniji.")
    print()

    print("=== Statistička snaga ===")
    p1, p2 = k1 / n1, k2 / n2
    n_min = min(n1, n2)
    print(f"Snaga za opaženu razliku uz n≈{n_min} po varijanti: "
          f"{power_two_proportions(p1, p2, n_min)*100:.1f} %")
    print(f"Potrebno po varijanti za snagu 80 %: {n_for_power(p1, p2):.0f} sesija "
          f"(ukupno {2*n_for_power(p1, p2):.0f})")
    down, up = mde(p1, n_min)
    if down is not None and up is not None:
        print(f"Uz n={n_min} po varijanti detektabilne su tek stope ispod "
              f"{down*100:.0f} % ili iznad {up*100:.0f} % "
              f"(polazna stopa {p1*100:.1f} %).")
    print()

    fig, ax = plt.subplots(figsize=(5.4, 4.2))
    rates = summary["conversion_rate"].values
    cis = [wilson_ci(int(r["conversions"]), int(r["total_sessions"]))
           for _, r in summary.iterrows()]
    err = np.array([[rates[i] - cis[i][0] for i in range(len(rates))],
                    [cis[i][1] - rates[i] for i in range(len(rates))]])
    ax.bar(summary.index, rates, color=["#4FA3F7", "#6E8C77"], width=0.55)
    ax.errorbar(range(len(rates)), rates, yerr=err, fmt="none",
                ecolor="#333333", capsize=6, linewidth=1.2)
    for i, (idx, row) in enumerate(summary.iterrows()):
        ax.text(i, cis[i][1] + 0.03,
                f"{row['conversion_rate']*100:.1f}%\n(n={int(row['total_sessions'])})",
                ha="center", fontsize=10)
    ax.set_ylim(0, 1.12)
    ax.set_ylabel("Stopa konverzije")
    ax.set_title(f"Konverzija po varijanti (Fisher p={p_fisher:.3f})\n"
                 "s 95 % intervalima pouzdanosti", fontsize=11)
    fig.tight_layout()
    fig.savefig("ab_conversion_comparison.png", dpi=150)
    plt.close(fig)
    print("Graf spremljen: ab_conversion_comparison.png")


if __name__ == "__main__":
    main()