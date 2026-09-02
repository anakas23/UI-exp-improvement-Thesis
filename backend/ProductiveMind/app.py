"""
ProductiveMind A/B test - backend server.

Pokretanje:
    pip install -r requirements.txt
    python app.py

Zatim otvori http://localhost:5000 u browseru.
Svaki novi posjet na "/" nasumično dodjeljuje varijantu A ili B.

ISPRAVLJENA VERZIJA - promjene u odnosu na prvu verziju:
  1. Vraćena nasumična dodjela varijante (bila je privremeno fiksirana na "B").
  2. Endpointi /track i /track_batch odbijaju događaje za sesiju koja je već
     završena. Time se na razini poslužitelja onemogućuje bilježenje ponašanja
     nakon donesene odluke, neovisno o tome radi li klijentska skripta ispravno
     (npr. ako ispitanik ima otvorenu istu poveznicu u dvije kartice).
  3. Uz svaki događaj bilježi se i vrijeme primitka na poslužitelju
     (stupac server_time), pa analiza više ne ovisi o satu ispitanikova
     računala, koji zna odstupati i po nekoliko minuta.
  4. Sigurnosni timeout mjeri se od zadnje aktivnosti (stupac last_seen), a ne
     od početka sesije. U prvoj verziji sesija se zatvarala 5 minuta nakon
     otvaranja stranice, pa je ispitanik koji je stranicu pažljivo čitao dulje
     od pet minuta bio automatski proglašen nekonvertiranim.
  5. Sesija zatvorena timeoutom ili napuštanjem stranice ostavlja converted
     kao NULL (izostanak odluke), umjesto da se upisuje 0 (odluka "ne").
"""

import os
import random
import sqlite3
import threading
import time
import uuid

from flask import Flask, jsonify, request, send_from_directory

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "productivemind.db")

# Sigurnosni timeout se sada mjeri od ZADNJE AKTIVNOSTI, pa je granica
# podignuta - ispitanik koji stranicu čita 10 minuta više se ne odbacuje.
SAFETY_TIMEOUT_SECONDS = 15 * 60
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
            ended_by TEXT,
            last_seen INTEGER
        );

        CREATE TABLE IF NOT EXISTS events (
            event_id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            x_percent REAL,
            y_percent REAL,
            scroll_percent REAL,
            timestamp INTEGER NOT NULL,
            server_time INTEGER,
            FOREIGN KEY (session_id) REFERENCES sessions(session_id)
        );

        CREATE INDEX IF NOT EXISTS idx_events_session ON events(session_id);
        """
    )

    # Nadogradnja postojeće baze koja je nastala starijom verzijom sheme -
    # bez ovoga bi se na već prikupljenim podacima server srušio pri prvom upisu.
    existing_sessions = [r[1] for r in conn.execute("PRAGMA table_info(sessions)")]
    if "last_seen" not in existing_sessions:
        conn.execute("ALTER TABLE sessions ADD COLUMN last_seen INTEGER")
        conn.execute("UPDATE sessions SET last_seen = start_time WHERE last_seen IS NULL")
    existing_events = [r[1] for r in conn.execute("PRAGMA table_info(events)")]
    if "server_time" not in existing_events:
        conn.execute("ALTER TABLE events ADD COLUMN server_time INTEGER")

    conn.commit()
    conn.close()


def session_is_open(conn, session_id):
    """Sesija prima nove događaje samo dok nije završena."""
    row = conn.execute(
        "SELECT end_time FROM sessions WHERE session_id = ?", (session_id,)
    ).fetchone()
    return row is not None and row["end_time"] is None


# ---------- stranice ----------

@app.route("/")
def intro():
    return send_from_directory("pages", "intro.html")


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
        "INSERT INTO sessions (session_id, variant, viewport_width, start_time, last_seen) "
        "VALUES (?, ?, ?, ?, ?)",
        (session_id, variant, viewport_width, now_ms, now_ms),
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

    now_ms = int(time.time() * 1000)
    conn = get_db()
    if not session_is_open(conn, data["session_id"]):
        conn.close()
        # Sesija je već završena - događaj se odbacuje. Vraća se 409 kako bi se
        # u razvoju odmah vidjelo da klijent i dalje šalje podatke.
        return jsonify({"ok": False, "error": "session closed"}), 409

    conn.execute(
        "INSERT INTO events (session_id, event_type, x_percent, y_percent, "
        "scroll_percent, timestamp, server_time) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            data["session_id"],
            data["event_type"],
            data.get("x_percent"),
            data.get("y_percent"),
            data.get("scroll_percent"),
            data["timestamp"],
            now_ms,
        ),
    )
    conn.execute(
        "UPDATE sessions SET last_seen = ? WHERE session_id = ?",
        (now_ms, data["session_id"]),
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

    now_ms = int(time.time() * 1000)
    conn = get_db()
    if not session_is_open(conn, session_id):
        conn.close()
        return jsonify({"ok": False, "error": "session closed"}), 409

    conn.executemany(
        "INSERT INTO events (session_id, event_type, x_percent, y_percent, "
        "scroll_percent, timestamp, server_time) "
        "VALUES (?, 'mousemove', ?, ?, NULL, ?, ?)",
        [
            (session_id, e.get("x_percent"), e.get("y_percent"),
             e.get("timestamp"), now_ms)
            for e in events
        ],
    )
    conn.execute(
        "UPDATE sessions SET last_seen = ? WHERE session_id = ?", (now_ms, session_id)
    )
    conn.commit()
    conn.close()
    return jsonify({"ok": True, "inserted": len(events)})


@app.route("/end_session", methods=["POST"])
def end_session():
    """
    Zatvara sesiju. ended_by = 'click' znači da je ispitanik sam donio odluku
    (jedino takve sesije ulaze u analizu); 'abandon' znači da je zatvorio ili
    napustio karticu bez odluke, pa converted ostaje NULL.
    """
    data = request.get_json(silent=True) or {}
    if "session_id" not in data:
        return jsonify({"ok": False, "error": "missing fields"}), 400

    ended_by = data.get("ended_by", "click")
    converted = data.get("converted")
    if ended_by == "click" and converted is None:
        return jsonify({"ok": False, "error": "missing converted"}), 400

    now_ms = int(time.time() * 1000)
    conn = get_db()
    # Uvjet end_time IS NULL osigurava da se prva odluka ne može naknadno
    # prepisati (npr. beaconom poslanim pri zatvaranju kartice).
    conn.execute(
        "UPDATE sessions SET converted = ?, end_time = ?, ended_by = ?, last_seen = ? "
        "WHERE session_id = ? AND end_time IS NULL",
        (
            None if converted is None else (1 if converted else 0),
            now_ms,
            ended_by,
            now_ms,
            data["session_id"],
        ),
    )
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


# ---------- safety timeout ----------

def safety_timeout_worker():
    """
    Zatvara sesije u kojima nije bilo nikakve aktivnosti dulje od
    SAFETY_TIMEOUT_SECONDS (npr. ispitanik je ostavio karticu otvorenu i otišao).
    Mjeri se vrijeme od ZADNJE AKTIVNOSTI, a ne od početka sesije, pa dugo
    čitanje stranice ne prekida mjerenje.

    converted ostaje NULL jer izostanak odluke nije odluka "ne".
    """
    while True:
        time.sleep(CHECK_INTERVAL_SECONDS)
        now_ms = int(time.time() * 1000)
        cutoff_ms = now_ms - SAFETY_TIMEOUT_SECONDS * 1000
        conn = get_db()
        conn.execute(
            "UPDATE sessions SET end_time = ?, ended_by = 'timeout' "
            "WHERE end_time IS NULL AND COALESCE(last_seen, start_time) < ?",
            (now_ms, cutoff_ms),
        )
        conn.commit()
        conn.close()


init_db()
timeout_thread = threading.Thread(target=safety_timeout_worker, daemon=True)
timeout_thread.start()


if __name__ == "__main__":
    # use_reloader=False - inače Flask pokreće proces dvaput, pa i pozadinska
    # dretva sigurnosnog timeouta radi u dvije instance.
    app.run(debug=True, port=5000, use_reloader=False)