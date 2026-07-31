"""
Generira heatmap slike (density mapa pozicije miša + klikova) za varijantu
A i varijantu B, na temelju podataka iz productivemind.db.

Pokretanje:
    python3 generate_heatmap.py

Rezultat: heatmap_variant_a.png i heatmap_variant_b.png u istom folderu.
"""

import sqlite3

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

DB_PATH = "productivemind.db"


def load_points(variant):
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql(
        """
        SELECT x_percent, y_percent, event_type
        FROM events
        WHERE (event_type = 'mousemove' OR event_type = 'click')
          AND x_percent IS NOT NULL
          AND session_id IN (SELECT session_id FROM sessions WHERE variant = ?)
        """,
        conn,
        params=(variant,),
    )
    conn.close()
    return df


def plot_heatmap(df, variant, out_path):
    if len(df) < 20:
        print(
            f"[Varijanta {variant}] Premalo podataka ({len(df)} točaka) "
            "za smislenu heatmapu - potrebno je barem par desetaka sesija."
        )
        return

    fig, ax = plt.subplots(figsize=(6, 9))

    sns.kdeplot(
        data=df,
        x="x_percent",
        y="y_percent",
        fill=True,
        cmap="rocket_r",
        thresh=0.02,
        levels=100,
        ax=ax,
    )

    # klikovi posebno istaknuti preko density mape
    clicks = df[df["event_type"] == "click"]
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
    ax.set_title(f"Heatmap pažnje - Varijanta {variant}  (n={len(df)} točaka)")

    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    print(f"[Varijanta {variant}] Spremljeno: {out_path} ({len(df)} točaka, {len(clicks)} klikova)")


if __name__ == "__main__":
    for variant in ("A", "B"):
        df = load_points(variant)
        plot_heatmap(df, variant, f"heatmap_variant_{variant.lower()}.png")