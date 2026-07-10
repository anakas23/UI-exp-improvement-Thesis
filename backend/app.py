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
import sqlite3

from flask import Flask, jsonify, request, send_from_directory

app = Flask(__name__, static_folder="static", static_url_path="")

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
            timestamp_ms INTEGER NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT PRIMARY KEY,
            page_variant TEXT NOT NULL,
            total_time_on_page REAL NOT NULL,
            task_success INTEGER NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()


init_db()


# --- Statične stranice ---

@app.route("/")
def index():
    return send_from_directory(app.static_folder, "variant-a.html")


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
        INSERT INTO raw_clicks (session_id, page_variant, zone, x, y, timestamp_ms)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            data["session_id"],
            data["page_variant"],
            data["zone"],
            data["x"],
            data["y"],
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
        INSERT OR REPLACE INTO sessions (session_id, page_variant, total_time_on_page, task_success)
        VALUES (?, ?, ?, ?)
        """,
        (
            data["session_id"],
            data["page_variant"],
            data["total_time_on_page"],
            1 if data["task_success"] else 0,
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
        "SELECT session_id, page_variant, zone, x, y, timestamp_ms FROM raw_clicks ORDER BY id"
    ).fetchall()
    conn.close()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["session_id", "page_variant", "zone", "x", "y", "timestamp_ms"])
    writer.writerows(rows)

    return buf.getvalue(), 200, {
        "Content-Type": "text/csv",
        "Content-Disposition": "attachment; filename=raw_clicks.csv",
    }


@app.route("/api/export/sessions.csv")
def export_sessions():
    conn = get_db()
    rows = conn.execute(
        "SELECT session_id, page_variant, total_time_on_page, task_success FROM sessions ORDER BY session_id"
    ).fetchall()
    conn.close()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["session_id", "page_variant", "total_time_on_page", "task_success"])
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
    app.run(debug=True, port=5000)