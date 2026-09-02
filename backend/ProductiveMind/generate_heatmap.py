"""
Generira toplinske mape (mapa gustoće pozicija miša + klikovi) za varijantu
A i varijantu B, na temelju podataka iz productivemind.db.

Pokretanje:
    python3 generate_heatmap.py

Rezultat: heatmap_variant_a.png i heatmap_variant_b.png u istom folderu.

ISPRAVLJENA VERZIJA:
  1. Koriste se samo događaji zabilježeni prije donesene odluke (učitavanje
     preko session_data.py). U staroj verziji mapa je sadržavala i pozicije
     miša zabilježene nakon klika, dok je ispitanik gledao poruku zahvale -
     u varijanti A to je bilo 81 % svih točaka. Te se točke skupljaju na
     mjestu gumba i na sredini skraćene stranice, pa su stvarale lažno
     žarište pažnje na dnu stranice.
  2. Uključene su samo sesije u kojima je ispitanik donio odluku, jednako
     kao u A/B analizi i modelu strojnog učenja. Stara verzija je u mape
     uključivala i sesije zatvorene sigurnosnim mehanizmom.
  3. Svaka sesija doprinosi mapi jednako (težina 1/broj točaka te sesije).
     Bez toga jedna sesija s tisućama zabilježenih točaka sama određuje
     izgled mape, pa mapa prikazuje ponašanje jednog ispitanika, a ne
     prosječno ponašanje skupine.
  4. Gustoća se računa samo iz pozicija miša; klikovi se prikazuju zasebno,
     da se isti podatak ne broji dvaput.
"""

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

import session_data

DB_PATH = "productivemind.db"
MIN_POINTS = 20


def plot_heatmap(events, variant, out_path):
    df = events[events["variant"] == variant]
    moves = df[(df["event_type"] == "mousemove") & df["x_percent"].notna()].copy()
    clicks = df[(df["event_type"] == "click") & df["x_percent"].notna()]

    n_sessions = moves["session_id"].nunique()

    if len(moves) < MIN_POINTS:
        print(f"[Varijanta {variant}] Premalo podataka ({len(moves)} točaka) "
              "za smislenu toplinsku mapu.")
        return

    # Jednak doprinos svake sesije, neovisno o tome koliko je dugo trajala.
    counts = moves.groupby("session_id")["x_percent"].transform("size")
    moves["weight"] = 1.0 / counts

    fig, ax = plt.subplots(figsize=(6, 9))

    sns.kdeplot(
        data=moves,
        x="x_percent",
        y="y_percent",
        weights="weight",
        fill=True,
        cmap="rocket_r",
        thresh=0.02,
        levels=100,
        ax=ax,
    )

    if len(clicks) > 0:
        ax.scatter(
            clicks["x_percent"],
            clicks["y_percent"],
            s=18,
            color="white",
            edgecolor="black",
            linewidth=0.6,
            zorder=5,
            label="klikovi",
        )
        ax.legend(loc="upper right", fontsize=8)

    ax.set_xlim(0, 1)
    ax.set_ylim(1, 0)  # invertirano - y=0 je vrh stranice
    ax.set_xlabel("x (relativno na širinu ekrana)")
    ax.set_ylabel("y (relativno na visinu stranice)")
    ax.set_title(f"Toplinska mapa pažnje - Varijanta {variant}\n"
                 f"({n_sessions} sesija, {len(moves)} točaka, "
                 f"jednaka težina po sesiji)", fontsize=11)

    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    print(f"[Varijanta {variant}] Spremljeno: {out_path} "
          f"({n_sessions} sesija, {len(moves)} točaka, {len(clicks)} klikova)")


def print_zone_summary(events):
    """Udio pažnje po vodoravnim zonama stranice - brojka koja se može navesti
    u radu umjesto opisnog dojma o tome gdje je pažnja bila najveća."""
    print("\n=== Udio pažnje po zonama stranice (jednaka težina po sesiji) ===")
    moves = events[(events["event_type"] == "mousemove") & events["y_percent"].notna()].copy()
    counts = moves.groupby("session_id")["y_percent"].transform("size")
    moves["weight"] = 1.0 / counts
    bins = [0, 0.25, 0.5, 0.75, 1.01]
    labels = ["gornja četvrtina", "druga četvrtina", "treća četvrtina", "donja četvrtina"]
    moves["zona"] = pd.cut(moves["y_percent"], bins=bins, labels=labels, right=False)
    table = (moves.groupby(["variant", "zona"], observed=False)["weight"].sum()
             .unstack(0))
    table = 100 * table / table.sum()
    print(table.round(1).to_string())


if __name__ == "__main__":
    events = session_data.load_events(DB_PATH, valid_only=True, decided_only=True)
    for variant in ("A", "B"):
        plot_heatmap(events, variant, f"heatmap_variant_{variant.lower()}.png")
    print_zone_summary(events)