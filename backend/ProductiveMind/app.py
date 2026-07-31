"""
ProductiveMind A/B test - backend server.

Pokretanje:
    pip install -r requirements.txt
    python app.py

Zatim otvori http://localhost:5000 u browseru.
Svaki novi posjet na "/" nasumično dodjeljuje varijantu A ili B.
"""

import os
import random
import sqlite3
import threading
import time
import uuid

from flask import Flask, jsonify, request, send_from_directory

# Apsolutna putanja izračunata iz lokacije ove datoteke - baza se time uvijek
# otvara/kreira na istom mjestu bez obzira odakle proces stvarno pokrenut
# (npr. WSGI server može imati drugačiji working directory od onog koji
# očekuješ, pa relativna putanja zna kreirati bazu na neočekivanom mjestu).
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "productivemind.db")
SAFETY_TIMEOUT_SECONDS = 5 * 60  # sigurnosni timeout - ne utječe na normalne podatke
CHECK_INTERVAL_SECONDS = 30

app = Flask(__name__, static_folder="pages", static_url_path="")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT PRIMARY KEY,
            variant TEXT NOT NULL,
            viewport_width INTEGER,
            start_time INTEGER NOT NULL,
            end_time INTEGER,
            converted INTEGER,
            ended_by TEXT
        );

        CREATE TABLE IF NOT EXISTS events (
            event_id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            x_percent REAL,
            y_percent REAL,
            scroll_percent REAL,
            timestamp INTEGER NOT NULL,
            FOREIGN KEY (session_id) REFERENCES sessions(session_id)
        );

        CREATE INDEX IF NOT EXISTS idx_events_session ON events(session_id);
        """
    )
    conn.commit()
    conn.close()


# ---------- stranice ----------

@app.route("/")
def intro():
    return send_from_directory("pages", "intro.html")


# variant_a.html i variant_b.html poslužuju se automatski preko static_folder,
# pošto su fizički u pages/ folderu (nema potrebe za posebnom rutom).


# ---------- API ----------

@app.route("/assign", methods=["POST"])
def assign():
    data = request.get_json(silent=True) or {}
    session_id = str(uuid.uuid4())
    variant = random.choice(["A", "B"])
    viewport_width = data.get("viewport_width")
    now_ms = int(time.time() * 1000)

    conn = get_db()
    conn.execute(
        "INSERT INTO sessions (session_id, variant, viewport_width, start_time) "
        "VALUES (?, ?, ?, ?)",
        (session_id, variant, viewport_width, now_ms),
    )
    conn.commit()
    conn.close()

    page = "variant_a.html" if variant == "A" else "variant_b.html"
    return jsonify(
        {
            "session_id": session_id,
            "variant": variant,
            "redirect_url": f"/{page}?sid={session_id}",
        }
    )


@app.route("/track", methods=["POST"])
def track():
    data = request.get_json(silent=True) or {}
    required = ("session_id", "event_type", "timestamp")
    if not all(k in data for k in required):
        return jsonify({"ok": False, "error": "missing fields"}), 400

    conn = get_db()
    conn.execute(
        "INSERT INTO events (session_id, event_type, x_percent, y_percent, "
        "scroll_percent, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
        (
            data["session_id"],
            data["event_type"],
            data.get("x_percent"),
            data.get("y_percent"),
            data.get("scroll_percent"),
            data["timestamp"],
        ),
    )
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@app.route("/track_batch", methods=["POST"])
def track_batch():
    """
    Prima paket uzoraka pozicije miša odjednom (umjesto jednog po jednom),
    da se izbjegne stotine zahtjeva u sekundi dok se miš pomiče.
    Očekuje: { "session_id": "...", "events": [ {x_percent, y_percent, timestamp}, ... ] }
    """
    data = request.get_json(silent=True) or {}
    session_id = data.get("session_id")
    events = data.get("events") or []
    if not session_id or not events:
        return jsonify({"ok": False, "error": "missing fields"}), 400

    conn = get_db()
    conn.executemany(
        "INSERT INTO events (session_id, event_type, x_percent, y_percent, "
        "scroll_percent, timestamp) VALUES (?, 'mousemove', ?, ?, NULL, ?)",
        [
            (session_id, e.get("x_percent"), e.get("y_percent"), e.get("timestamp"))
            for e in events
        ],
    )
    conn.commit()
    conn.close()
    return jsonify({"ok": True, "inserted": len(events)})


@app.route("/end_session", methods=["POST"])
def end_session():
    data = request.get_json(silent=True) or {}
    if "session_id" not in data or "converted" not in data:
        return jsonify({"ok": False, "error": "missing fields"}), 400

    now_ms = int(time.time() * 1000)
    conn = get_db()
    conn.execute(
        "UPDATE sessions SET converted = ?, end_time = ?, ended_by = ? "
        "WHERE session_id = ? AND converted IS NULL",
        (
            1 if data["converted"] else 0,
            now_ms,
            data.get("ended_by", "click"),
            data["session_id"],
        ),
    )
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


# ---------- safety timeout ----------

def safety_timeout_worker():
    """
    Tiho u pozadini zatvara sesije koje su ostale otvorene predugo
    (npr. korisnik ostavio tab otvoren bez klika na gumb).
    Ne utječe na normalno ponašanje - aktivira se tek nakon
    SAFETY_TIMEOUT_SECONDS neaktivnosti.
    """
    while True:
        time.sleep(CHECK_INTERVAL_SECONDS)
        cutoff_ms = int(time.time() * 1000) - SAFETY_TIMEOUT_SECONDS * 1000
        now_ms = int(time.time() * 1000)
        conn = get_db()
        conn.execute(
            "UPDATE sessions SET converted = 0, end_time = ?, ended_by = 'timeout' "
            "WHERE converted IS NULL AND start_time < ?",
            (now_ms, cutoff_ms),
        )
        conn.commit()
        conn.close()


# Ovo se izvrši i kad se app.py pokrene direktno (python app.py) i kad ga
# produkcijski server (npr. PythonAnywhere) samo importira - inače se baza
# nikad ne bi kreirala i safety timeout nikad ne bi krenuo u produkciji.
init_db()
timeout_thread = threading.Thread(target=safety_timeout_worker, daemon=True)
timeout_thread.start()


if __name__ == "__main__":
    app.run(debug=True, port=5000)