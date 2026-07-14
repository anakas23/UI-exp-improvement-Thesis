"""
app.py
------
Lagani backend za prikupljanje podataka o klikovima (Faza 2).

Sprema podatke u SQLite bazu (heatmap.db, stvara se automatski uz
prvo pokretanje). Poslužuje i statične HTML/CSS/JS fileove iz static/
foldera, tako da se cijeli projekt pokreće s jednim `python app.py`.

Endpointi:
  POST /api/log-click          - zapisuje jedan klik (raw_clicks tablica)
  POST /api/log-session        - zapisuje/ažurira sažetak sesije (sessions tablica)
  GET  /api/export/raw-clicks.csv  - izvoz svih klikova u CSV (za Fazu 3 - heatmape)
  GET  /api/export/sessions.csv    - izvoz svih sesija u CSV (za Fazu 4 - ML dataset)
  GET  /api/stats              - brzi pregled (broj sesija, broj klikova)

Pokretanje:
  pip install flask
  python app.py
  otvori http://localhost:5000/variant-a.html (ili variant-b.html / variant-c.html)
"""

import csv
import io
import os
import random
import sqlite3

from flask import Flask, jsonify, request, send_from_directory, session

app = Flask(__name__, static_folder="static", static_url_path="")

# Potrebno za session cookie (pamti koja je varijanta dodijeljena svakom
# posjetitelju - da refresh ne dodijeli drugu varijantu istoj osobi).
app.secret_key = os.environ.get("SECRET_KEY", "heatmap-thesis-dev-key-change-if-needed")

VARIANT_FILES = ["variant-a.html", "variant-b.html", "variant-c.html"]

DB_PATH = os.path.join(os.path.dirname(__file__), "heatmap.db")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS raw_clicks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            page_variant TEXT NOT NULL,
            zone TEXT NOT NULL,
            x INTEGER NOT NULL,
            y INTEGER NOT NULL,
            page_width INTEGER,
            page_height INTEGER,
            zone_rel_x REAL,
            zone_rel_y REAL,
            timestamp_ms INTEGER NOT NULL
        )
        """
    )

    # Migracija: dodaj nove kolone ako baza postoji iz vremena prije ove
    # izmjene (bez brisanja postojećih podataka).
    click_columns = [row["name"] for row in conn.execute("PRAGMA table_info(raw_clicks)")]
    if "page_width" not in click_columns:
        conn.execute("ALTER TABLE raw_clicks ADD COLUMN page_width INTEGER")
    if "page_height" not in click_columns:
        conn.execute("ALTER TABLE raw_clicks ADD COLUMN page_height INTEGER")
    if "zone_rel_x" not in click_columns:
        conn.execute("ALTER TABLE raw_clicks ADD COLUMN zone_rel_x REAL")
    if "zone_rel_y" not in click_columns:
        conn.execute("ALTER TABLE raw_clicks ADD COLUMN zone_rel_y REAL")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT PRIMARY KEY,
            page_variant TEXT NOT NULL,
            total_time_on_page REAL NOT NULL,
            task_success INTEGER NOT NULL,
            attempt_number INTEGER
        )
        """
    )

    # Migracija: ako baza već postoji iz vremena prije attempt_number kolone,
    # dodaj je bez brisanja postojećih podataka. Stari redovi dobivaju NULL
    # (nepoznat redoslijed) umjesto lažnog 1 - da se jasno razlikuju od
    # stvarno poznatih prvih pokušaja.
    existing_columns = [row["name"] for row in conn.execute("PRAGMA table_info(sessions)")]
    if "attempt_number" not in existing_columns:
        conn.execute("ALTER TABLE sessions ADD COLUMN attempt_number INTEGER")

    conn.commit()
    conn.close()


init_db()


# --- Glavni link za testere: nasumična dodjela JEDNE varijante ---

@app.route("/")
@app.route("/test")
def random_variant():
    """
    Ovo je link koji se dijeli testerima. Svaki NOVI posjetitelj (novi
    browser/uređaj, nema još cookie) dobiva NASUMIČNO jednu od tri
    varijante, s jednakom vjerojatnošću (~33% svaka).

    Cookie ("session" - Flaskov potpisani cookie) pamti dodijeljenu
    varijantu za tog posjetitelja, tako da eventualni refresh stranice
    ne promijeni layout usred testiranja iste osobe - svaka osoba i dalje
    rješava SAMO jednu varijantu, kao što je dizajn zahtijeva (between-
    -subjects test, bez efekta učenja od prethodnih varijanti).
    """
    if "assigned_variant" not in session:
        session["assigned_variant"] = random.choice(VARIANT_FILES)
    return send_from_directory(app.static_folder, session["assigned_variant"])


@app.route("/admin/reset-assignment")
def reset_assignment():
    """Pomoćna ruta za TVOJE testiranje - briše cookie dodjele u TVOM
    browseru, tako da sljedeći put kad odeš na '/' dobiješ novu nasumičnu
    varijantu (korisno kad sam želiš isprobati sve tri bez otvaranja
    incognito prozora svaki put)."""
    session.pop("assigned_variant", None)
    return jsonify({"status": "assignment cookie cleared, reload / to get a new random variant"})


# --- API: primanje podataka ---

@app.route("/api/log-click", methods=["POST"])
def log_click():
    data = request.get_json(force=True)
    required = ("session_id", "page_variant", "zone", "x", "y", "timestamp_ms")
    if not all(k in data for k in required):
        return jsonify({"error": "missing fields"}), 400

    conn = get_db()
    conn.execute(
        """
        INSERT INTO raw_clicks
            (session_id, page_variant, zone, x, y, page_width, page_height, zone_rel_x, zone_rel_y, timestamp_ms)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            data["session_id"],
            data["page_variant"],
            data["zone"],
            data["x"],
            data["y"],
            data.get("page_width"),
            data.get("page_height"),
            data.get("zone_rel_x"),
            data.get("zone_rel_y"),
            data["timestamp_ms"],
        ),
    )
    conn.commit()
    conn.close()
    return jsonify({"status": "ok"})


@app.route("/api/log-session", methods=["POST"])
def log_session():
    data = request.get_json(force=True)
    required = ("session_id", "page_variant", "total_time_on_page", "task_success")
    if not all(k in data for k in required):
        return jsonify({"error": "missing fields"}), 400

    conn = get_db()
    conn.execute(
        """
        INSERT OR REPLACE INTO sessions (session_id, page_variant, total_time_on_page, task_success, attempt_number)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            data["session_id"],
            data["page_variant"],
            data["total_time_on_page"],
            1 if data["task_success"] else 0,
            data.get("attempt_number"),  # None ako nije poslano (stariji frontend)
        ),
    )
    conn.commit()
    conn.close()
    return jsonify({"status": "ok"})


# --- API: izvoz podataka ---

@app.route("/api/export/raw-clicks.csv")
def export_raw_clicks():
    conn = get_db()
    rows = conn.execute(
        "SELECT session_id, page_variant, zone, x, y, page_width, page_height, zone_rel_x, zone_rel_y, timestamp_ms "
        "FROM raw_clicks ORDER BY id"
    ).fetchall()
    conn.close()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "session_id", "page_variant", "zone", "x", "y",
        "page_width", "page_height", "zone_rel_x", "zone_rel_y", "timestamp_ms",
    ])
    writer.writerows(rows)

    return buf.getvalue(), 200, {
        "Content-Type": "text/csv",
        "Content-Disposition": "attachment; filename=raw_clicks.csv",
    }


@app.route("/api/export/sessions.csv")
def export_sessions():
    conn = get_db()
    rows = conn.execute(
        "SELECT session_id, page_variant, total_time_on_page, task_success, attempt_number FROM sessions ORDER BY session_id"
    ).fetchall()
    conn.close()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["session_id", "page_variant", "total_time_on_page", "task_success", "attempt_number"])
    writer.writerows(rows)

    return buf.getvalue(), 200, {
        "Content-Type": "text/csv",
        "Content-Disposition": "attachment; filename=sessions.csv",
    }


# --- API: brza statistika (korisno za praćenje testiranja uživo) ---

@app.route("/api/stats")
def stats():
    conn = get_db()
    total_sessions = conn.execute("SELECT COUNT(*) AS c FROM sessions").fetchone()["c"]
    total_clicks = conn.execute("SELECT COUNT(*) AS c FROM raw_clicks").fetchone()["c"]
    per_variant = conn.execute(
        "SELECT page_variant, COUNT(*) AS c FROM sessions GROUP BY page_variant"
    ).fetchall()
    conn.close()
    return jsonify(
        {
            "total_sessions": total_sessions,
            "total_clicks": total_clicks,
            "sessions_per_variant": {row["page_variant"]: row["c"] for row in per_variant},
        }
    )


if __name__ == "__main__":
    # host="0.0.0.0" čini server dostupnim i drugim uređajima na istoj mreži,
    # ne samo tvom računalu (potrebno za dijeljenje s testerima).
    # debug=False je NAMJERNO - Flaskov debug mod uključuje interaktivnu
    # konzolu koja bi, ako je server dostupan drugima (LAN ili ngrok),
    # dopustila izvršavanje proizvoljnog koda na tvom računalu.
    app.run(host="0.0.0.0", port=5000, debug=False)