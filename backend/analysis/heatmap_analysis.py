"""
heatmap_analysis.py
--------------------
Faza 3: generira heatmap vizualizacije i zone-usporedbu iz prikupljenih
klikova (raw_clicks.csv), za sve tri varijante odjednom.

Pokretanje:
    python heatmap_analysis.py putanja/do/raw_clicks.csv putanja/do/output_foldera

Ako se argumenti ne navedu, koristi zadane putanje "data/raw_clicks.csv" i "output/".

Izlaz (u output folderu):
    normalized_heatmap_variant_a.png, _b.png, _c.png
        - prostorna gustoća klikova, pozicija normalizirana na postotak (0-1)
          stranice (x/page_width, y/page_height) - usporedivo bez obzira je li
          tester bio na mobitelu ili velikom monitoru
    zone_comparison.png
        - broj klikova po zoni, sve tri varijante jedna pored druge (bar chart)

NAPOMENE O KVALITETI PODATAKA:
1. Normalizirana heatmapa zahtijeva da klik ima zabilježen page_width/
   page_height (dodano u click-logger.js). Redovi koji to nemaju (stariji,
   prije te izmjene prikupljeni podaci) se automatski preskaču za taj graf -
   ispisuje se poruka o tome, skripta ne pada.
2. Skripta automatski izbacuje sesije s neobično velikim brojem klikova
   (zadano: >30 klikova, MAX_CLICKS_PER_SESSION), jer takve sesije obično
   nisu stvarni ispitanici nego test/debug klikanje - ispisuje se upozorenje
   za svaku izbačenu sesiju.
"""

import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap
from scipy.stats import gaussian_kde

ZONE_ORDER = ["nav", "hero", "sidebar", "products", "cta", "footer"]
MAX_CLICKS_PER_SESSION = 30  # sesije s više klikova od ovoga smatraju se test/debug podacima

# Relativne (0-1) bounding-box koordinate zona za svaku varijantu, ručno
# preslikane iz stvarnog CSS grid rasporeda (grid-template-areas) definiranog
# u variant-a/b/c.html. Format: (x0, x1, y0, y1), y=0 je vrh stranice.
# Koristi se SAMO za crtanje sheme stranice u pozadini (nije stvarni
# screenshot), stvarne pozicije klikova (x_norm, y_norm) crtaju se preko
# ovoga na temelju pravih izmjerenih podataka.
# Relativne (0-1) bounding-box koordinate zona za svaku varijantu, ručno
# preslikane iz stvarnog CSS grid rasporeda (grid-template-areas) definiranog
# u variant-a/b/c.html. Format: (x0, x1, y0, y1), y=0 je vrh stranice.
#
# NAPOMENA: budući da varijante sad imaju RAZLIČIT redoslijed kategorija
# (namjerno - vidi catalog.js), njihova ukupna visina prirodno malo varira
# međusobno - to je u redu jer je to legitimna razlika u dizajnu, ne
# metodološki problem (problem koji smo rješavali bio je promjena visine
# UNUTAR iste sesije, ne razlika u visini IZMEĐU varijanti). Proporcije
# ispod su ilustrativne aproksimacije za shematski prikaz, ne utječu na
# točnost stvarnih podataka (to jamči zone_rel_x/y mehanizam).
#
# "cta" (gumb Kupi) dijeli ISTI bounding box kao "products" - gumb je
# izravno na kartici, nema zasebnog modala.
ZONE_LAYOUTS = {
    "variant_a": {
        "nav": (0.00, 1.00, 0.00, 0.06),
        "hero": (0.00, 1.00, 0.06, 0.16),
        "sidebar": (0.00, 1.00, 0.16, 0.20),
        "products": (0.00, 1.00, 0.20, 0.90),
        "cta": (0.00, 1.00, 0.20, 0.90),
        "footer": (0.00, 1.00, 0.90, 1.00),
    },
    "variant_b": {
        "nav": (0.00, 1.00, 0.00, 0.05),
        "hero": (0.00, 1.00, 0.05, 0.12),
        "sidebar": (0.00, 0.18, 0.12, 0.90),
        "products": (0.18, 1.00, 0.12, 0.90),
        "cta": (0.18, 1.00, 0.12, 0.90),
        "footer": (0.00, 1.00, 0.90, 1.00),
    },
    "variant_c": {
        "nav": (0.00, 0.20, 0.00, 0.55),
        "sidebar": (0.00, 0.20, 0.55, 0.90),
        "hero": (0.20, 1.00, 0.00, 0.15),
        "products": (0.20, 1.00, 0.15, 0.90),
        "cta": (0.20, 1.00, 0.15, 0.90),
        "footer": (0.00, 1.00, 0.90, 1.00),
    },
}

# Colormap u stilu heatmap.js - providno tamo gdje nema klikova (pozadina/shema
# stranice ostaje vidljiva), plavo->zeleno->žuto->crveno kako gustoća raste.
HEATMAP_CMAP = LinearSegmentedColormap.from_list(
    "heatmapjs",
    [
        (0.00, (0.10, 0.20, 0.90, 0.00)),
        (0.15, (0.10, 0.55, 0.95, 0.35)),
        (0.35, (0.15, 0.85, 0.55, 0.55)),
        (0.55, (0.75, 0.95, 0.15, 0.65)),
        (0.75, (1.00, 0.65, 0.10, 0.75)),
        (1.00, (0.95, 0.10, 0.10, 0.85)),
    ],
)


def load_clicks(path):
    df = pd.read_csv(path)
    # Stariji CSV-ovi (prikupljeni prije uvođenja zone_rel_x/y) nemaju ove
    # kolone - dodaj ih kao prazne (NaN) da skripta ne padne; heatmapa će te
    # retke jednostavno preskočiti.
    for col in ("page_width", "page_height", "zone_rel_x", "zone_rel_y"):
        if col not in df.columns:
            df[col] = pd.NA
    return df


def filter_outlier_sessions(df, max_clicks=MAX_CLICKS_PER_SESSION):
    """Izbacuje sesije s nerealno velikim brojem klikova (vjerojatno test/debug klikanje,
    ne stvarno korisničko ponašanje na jednom jednostavnom zadatku)."""
    counts = df.groupby("session_id").size()
    outlier_ids = counts[counts > max_clicks].index.tolist()

    for sid in outlier_ids:
        print(f"  [upozorenje] Izbačena sesija {sid} - {counts[sid]} klikova (> {max_clicks}), "
              f"vjerojatno test/debug podatak, ne stvarni ispitanik.")

    return df[~df["session_id"].isin(outlier_ids)]


def draw_page_mockup(ax, layout):
    """Crta shematski okvir preglednika (kao mockup screenshot-a) preko kojeg
    se zatim preklapa prava heatmapa. Nije stvaran screenshot stranice (ovo
    okruženje ne može pokrenuti headless browser), ali vjerno prikazuje
    stvarni raspored zona iz CSS-a te varijante."""
    # Vanjski okvir "prozora preglednika"
    frame = plt.Rectangle(
        (-0.02, -0.07), 1.04, 1.14, facecolor="white",
        edgecolor="#b0b8c0", linewidth=1.5, zorder=0,
    )
    ax.add_patch(frame)

    # Gornja traka s tri "tockice" (kao naslovna traka preglednika)
    top_bar = plt.Rectangle(
        (-0.02, -0.07), 1.04, 0.05, facecolor="#f3f4f6",
        edgecolor="#b0b8c0", linewidth=1, zorder=1,
    )
    ax.add_patch(top_bar)
    for cx, color in zip([0.005, 0.025, 0.045], ["#ff5f57", "#febc2e", "#28c840"]):
        ax.add_patch(plt.Circle((cx, -0.045), 0.007, color=color, zorder=2))

    # Obrisi zona prema stvarnom CSS rasporedu ("cta" je izostavljen iz
    # crtanja - to je modal koji lebdi preko cijelog ekrana, ne dio stranice
    # sa stalnom pozicijom, ali i dalje ima bounding box u ZONE_LAYOUTS radi
    # mapiranja pozicije klika)
    for zone, (x0, x1, y0, y1) in layout.items():
        if zone == "cta":
            continue
        rect = plt.Rectangle(
            (x0, y0), x1 - x0, y1 - y0, fill=False,
            edgecolor="#c7ccd1", linewidth=1, zorder=1,
        )
        ax.add_patch(rect)
        ax.text(
            (x0 + x1) / 2, (y0 + y1) / 2, zone,
            ha="center", va="center", fontsize=8, color="#9aa0a6", zorder=1,
        )


def generate_page_heatmap(df, variant, output_dir, grid_n=150):
    """Heatmapa preklopljena preko sheme stranice (u stilu 'heatmap.js').

    Koristi zone_rel_x/zone_rel_y - poziciju klika RELATIVNU na zonu koja je
    kliknuta (0-1 unutar granica te zone), a ne poziciju na cijeloj stranici.
    To jamči da klik uvijek pada unutar pravog pravokutnika sheme, neovisno
    o tome je li se visina stranice u međuvremenu promijenila (SPA sadržaj)
    ili je tester bio na drugom uređaju.

    final_x/final_y se dobiju kombiniranjem zone_rel_x/y sa ZONE_LAYOUTS
    bounding-boxom te zone: final = zone_x0 + zone_rel_x * (zone_x1 - zone_x0)."""
    layout = ZONE_LAYOUTS[variant]

    subset = df[
        (df["page_variant"] == variant)
        & df["zone_rel_x"].notna()
        & df["zone_rel_y"].notna()
        & df["zone"].isin(layout.keys())
    ].copy()

    total_variant_rows = (df["page_variant"] == variant).sum()
    if subset.empty:
        print(f"  Nema klikova sa zone_rel_x/y za {variant} (od ukupno {total_variant_rows}), preskačem.")
        return
    if len(subset) < total_variant_rows:
        print(f"  Napomena: {total_variant_rows - len(subset)} od {total_variant_rows} klikova za {variant} "
              f"nema zone_rel_x/y (stariji podaci) - preskočeni za ovaj graf.")

    def to_final_xy(row):
        x0, x1, y0, y1 = layout[row["zone"]]
        return pd.Series({
            "final_x": x0 + row["zone_rel_x"] * (x1 - x0),
            "final_y": y0 + row["zone_rel_y"] * (y1 - y0),
        })

    subset[["final_x", "final_y"]] = subset.apply(to_final_xy, axis=1)

    fig, ax = plt.subplots(figsize=(6, 9))
    draw_page_mockup(ax, layout)

    if len(subset) >= 3:
        xy = np.vstack([subset["final_x"], subset["final_y"]])
        kde = gaussian_kde(xy, bw_method=0.12)

        xx = np.linspace(0, 1, grid_n)
        yy = np.linspace(0, 1, grid_n)
        xx_grid, yy_grid = np.meshgrid(xx, yy)
        positions = np.vstack([xx_grid.ravel(), yy_grid.ravel()])
        density = kde(positions).reshape(xx_grid.shape)
        density = density / density.max()

        ax.contourf(xx_grid, yy_grid, density, levels=25, cmap=HEATMAP_CMAP, zorder=5)
    else:
        print(f"  [napomena] Samo {len(subset)} klika za {variant} - premalo za glatku "
              f"heatmapu, prikazujem samo pojedinačne točke.")

    ax.scatter(subset["final_x"], subset["final_y"], s=12, color="#222", alpha=0.5, zorder=6)

    ax.set_xlim(-0.03, 1.03)
    ax.set_ylim(1.08, -0.09)  # y=0 je vrh stranice
    ax.axis("off")
    ax.set_title(f"{variant} - heatmap na izgledu stranice\n({len(subset)} klikova)")

    fig.tight_layout()
    out_path = os.path.join(output_dir, f"page_heatmap_{variant}.png")
    fig.savefig(out_path, dpi=150, facecolor="white")
    plt.close(fig)
    print(f"  Spremljeno: {out_path}")


def generate_zone_comparison(df, output_dir):
    counts = df.groupby(["page_variant", "zone"]).size().unstack(fill_value=0)
    counts = counts.reindex(columns=ZONE_ORDER, fill_value=0)

    fig, ax = plt.subplots(figsize=(10, 6))
    counts.T.plot(kind="bar", ax=ax)
    ax.set_title("Broj klikova po zoni - usporedba varijanti A/B/C")
    ax.set_xlabel("Zona")
    ax.set_ylabel("Broj klikova")
    ax.legend(title="Varijanta")
    ax.tick_params(axis="x", rotation=0)

    fig.tight_layout()
    out_path = os.path.join(output_dir, "zone_comparison.png")
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    print(f"  Spremljeno: {out_path}")


def main():
    raw_clicks_path = sys.argv[1] if len(sys.argv) > 1 else "data/raw_clicks.csv"
    output_dir = sys.argv[2] if len(sys.argv) > 2 else "output"
    os.makedirs(output_dir, exist_ok=True)

    print(f"Učitavam: {raw_clicks_path}")
    df = load_clicks(raw_clicks_path)
    print(f"Ukupno redaka (klikova): {len(df)}")

    print("\nProvjera outlier sesija...")
    df = filter_outlier_sessions(df)
    print(f"Redaka nakon filtriranja: {len(df)}")

    print("\nGeneriram heatmape preko sheme stranice (stvarne pozicije klika)...")
    for variant in sorted(df["page_variant"].unique()):
        generate_page_heatmap(df, variant, output_dir)

    print("\nGeneriram usporedbu po zonama...")
    generate_zone_comparison(df, output_dir)

    print(f"\nGotovo. Sve slike su u: {output_dir}")


if __name__ == "__main__":
    main()