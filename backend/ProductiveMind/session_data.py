"""
Zajednički modul za učitavanje i čišćenje podataka iz productivemind.db.

Sve tri analitičke skripte (ab_test_analysis.py, generate_heatmap.py,
ml_analysis.py) učitavaju podatke isključivo preko ovog modula, kako bi
kriterij uključivanja sesija i događaja bio identičan u svim analizama.

Ovdje su riješena tri problema uočena u sirovim podacima:

1) DOGAĐAJI ZABILJEŽENI NAKON KRAJA SESIJE
   Stara verzija stranice nije zaustavljala mjerenje nakon što ispitanik
   klikne jedan od dva gumba, pa su se pozicije miša nastavile bilježiti
   sve dok je kartica preglednika ostala otvorena na poruci zahvale
   (u jednom slučaju više od tri dana). Ti događaji nastaju NAKON ishoda
   koji se mjeri i moraju se ukloniti.

2) RAZLIKA SATOVA KLIJENTA I POSLUŽITELJA
   Vremenske oznake događaja (timestamp) dolaze iz preglednika ispitanika
   (Date.now()), a start_time i end_time postavlja poslužitelj. Satovi se
   ne poklapaju - u prikupljenim podacima razlika ide od -12 minuta do
   +12 minuta. Zbog toga se granica "kraja sesije" ne smije uspoređivati
   izravno; za svaku se sesiju procjenjuje pomak sata (delta) i granica se
   za taj iznos pomiče.

   Napomena: u novoj verziji app.py poslužitelj uz svaki događaj bilježi i
   vlastito vrijeme primitka (stupac server_time). Ako je taj stupac
   popunjen, koristi se on i procjena pomaka nije potrebna.

3) SESIJE BEZ STVARNE ODLUKE
   Sesije koje je zatvorio sigurnosni mehanizam (ended_by='timeout') ili
   koje je ispitanik napustio (ended_by='abandon') ne sadrže odluku
   "da/ne", nego njezin izostanak, pa se isključuju iz svih analiza.
"""

import sqlite3

import pandas as pd

# Tolerancija u milisekundama. Uzorci miša nakupljeni prije klika šalju se
# u paketu tek pri završetku sesije, pa njihova vremenska oznaka može biti
# koju stotinu milisekundi iza trenutka klika zabilježenog na poslužitelju.
TOLERANCE_MS = 3000

# Sesije koje ulaze u analizu: samo one u kojima je ispitanik sam kliknuo
# jedan od dva gumba.
DECIDED = ("click",)


def _has_column(conn, table, column):
    cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]
    return column in cols


def load_sessions(db_path, decided_only=True):
    """Vraća DataFrame sesija. Ako je decided_only, samo sesije s odlukom."""
    conn = sqlite3.connect(db_path)
    df = pd.read_sql("SELECT * FROM sessions", conn)
    conn.close()
    if decided_only:
        df = df[df["ended_by"].isin(DECIDED) & df["converted"].notna()].copy()
    return df


def load_events(db_path, valid_only=True, decided_only=True):
    """
    Vraća DataFrame događaja spojen s podacima o sesiji.

    valid_only=True zadržava samo događaje zabilježene do trenutka odluke
    (uz korekciju pomaka sata i toleranciju), tj. uklanja događaje nastale
    nakon završetka sesije.
    """
    conn = sqlite3.connect(db_path)
    use_server_time = _has_column(conn, "events", "server_time")

    query = """
        SELECT
            e.event_id, e.session_id, e.event_type,
            e.x_percent, e.y_percent, e.scroll_percent, e.timestamp,
            {server_time_col}
            s.variant, s.converted, s.ended_by, s.start_time, s.end_time,
            s.viewport_width
        FROM events e
        JOIN sessions s ON s.session_id = e.session_id
    """.format(server_time_col="e.server_time," if use_server_time else "")

    df = pd.read_sql(query, conn)
    conn.close()

    if decided_only:
        df = df[df["ended_by"].isin(DECIDED) & df["converted"].notna()].copy()

    if not valid_only:
        return df

    if use_server_time and df["server_time"].notna().any():
        # Poslužiteljsko vrijeme primitka - nema problema s razlikom satova.
        ref = df["server_time"].fillna(df["timestamp"])
        cutoff = df["end_time"] + TOLERANCE_MS
        df = df[ref <= cutoff].copy()
    else:
        # Procjena pomaka sata po sesiji: prvi zabilježeni događaj nastaje
        # neposredno nakon otvaranja stranice, pa je razlika između njegove
        # vremenske oznake i start_time dobra procjena pomaka.
        delta = df.groupby("session_id")["timestamp"].transform("min") - df["start_time"]
        cutoff = df["end_time"] + delta + TOLERANCE_MS
        df = df[df["timestamp"] <= cutoff].copy()

    return df


def session_features(db_path):
    """
    Značajke na razini sesije, izračunate isključivo iz događaja
    zabilježenih prije donošenja odluke.
    """
    sessions = load_sessions(db_path, decided_only=True)
    events = load_events(db_path, valid_only=True, decided_only=True)

    mm = events[events["event_type"] == "mousemove"]
    clicks = events[events["event_type"] == "click"]
    scrolls = events[events["event_type"] == "scroll"]

    feat = pd.DataFrame({"session_id": sessions["session_id"].values})
    feat["variant"] = sessions["variant"].values
    feat["converted"] = sessions["converted"].astype(int).values
    feat["time_to_decision"] = (
        (sessions["end_time"] - sessions["start_time"]) / 1000.0
    ).values

    feat = feat.merge(
        scrolls.groupby("session_id")["scroll_percent"].max().rename("scroll_depth"),
        on="session_id", how="left",
    )
    feat = feat.merge(
        clicks.groupby("session_id").size().rename("num_clicks"),
        on="session_id", how="left",
    )
    feat = feat.merge(
        mm.groupby("session_id").size().rename("mouse_activity_count"),
        on="session_id", how="left",
    )
    feat = feat.merge(
        mm.groupby("session_id")["y_percent"].mean().rename("avg_hover_y"),
        on="session_id", how="left",
    )

    feat["scroll_depth"] = feat["scroll_depth"].fillna(0.0)
    feat["num_clicks"] = feat["num_clicks"].fillna(0).astype(int)
    feat["mouse_activity_count"] = feat["mouse_activity_count"].fillna(0).astype(int)
    # Sesija bez ijednog zabilježenog pokreta miša nema izmjerenu prosječnu
    # poziciju pokazivača. Popunjavanje nulom stavilo bi je na sam vrh
    # stranice, što je izmišljen podatak, pa se koristi medijan skupa.
    feat["avg_hover_y"] = feat["avg_hover_y"].fillna(feat["avg_hover_y"].median())

    feat["variant_encoded"] = feat["variant"].map({"A": 0, "B": 1})
    return feat


def data_quality_report(db_path):
    """Pregled koliko je podataka odbačeno i zašto - za poglavlje o metodologiji."""
    conn = sqlite3.connect(db_path)
    all_sessions = pd.read_sql("SELECT variant, ended_by FROM sessions", conn)
    conn.close()

    all_events = load_events(db_path, valid_only=False, decided_only=True)
    valid_events = load_events(db_path, valid_only=True, decided_only=True)

    lines = []
    lines.append("=== Pregled sesija ===")
    lines.append(str(all_sessions.groupby(["variant", "ended_by"]).size()
                     .rename("broj").to_frame()))
    lines.append("")
    lines.append("=== Događaji u sesijama s odlukom ===")
    a = all_events.groupby(["variant", "event_type"]).size().rename("sve")
    v = valid_events.groupby(["variant", "event_type"]).size().rename("valjano")
    cmp_df = pd.concat([a, v], axis=1).fillna(0).astype(int)
    cmp_df["odbačeno"] = cmp_df["sve"] - cmp_df["valjano"]
    cmp_df["% odbačeno"] = (100 * cmp_df["odbačeno"] / cmp_df["sve"]).round(1)
    lines.append(str(cmp_df))
    return "\n".join(lines)


if __name__ == "__main__":
    print(data_quality_report("productivemind.db"))