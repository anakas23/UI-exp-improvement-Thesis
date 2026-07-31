"""
Generira sintetičke (lažne) sesije i mousemove/click evente izravno u bazu,
da se heatmap skripta može odmah vizualno provjeriti prije nego se
podaci prikupljaju od stvarnih testera.

Pokretanje:
    python3 seed_test_data.py

VAŽNO: ovo ubacuje TESTNE podatke u productivemind.db. Prije nego pustiš
prave testere, obriši bazu (rm productivemind.db) da krene prazna -
inače će se sintetički podaci pomiješati sa stvarnima.
"""

import random
import sqlite3
import time
import uuid

DB_PATH = "productivemind.db"

# Regije pažnje (x_percent, y_percent, raspršenost) - grubo odgovaraju
# stvarnom rasporedu elemenata na varijantama A i B.
REGIONS = {
    "A": [
        (0.25, 0.10, 0.06),  # naslov
        (0.22, 0.22, 0.05),  # spec-list
        (0.75, 0.20, 0.08),  # mock dashboard desno
        (0.20, 0.50, 0.10),  # feature grid
        (0.50, 0.88, 0.05),  # CTA dno
    ],
    "B": [
        (0.50, 0.10, 0.07),  # naslov
        (0.50, 0.35, 0.08),  # testimonijali
        (0.50, 0.80, 0.05),  # CTA dno
    ],
}


def random_point(regions):
    cx, cy, spread = random.choice(regions)
    x = min(max(random.gauss(cx, spread), 0), 1)
    y = min(max(random.gauss(cy, spread), 0), 1)
    return x, y


def seed(num_sessions_per_variant=30):
    conn = sqlite3.connect(DB_PATH)
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
        """
    )

    now = int(time.time() * 1000)

    for variant, base_conversion in (("A", 0.35), ("B", 0.55)):
        for _ in range(num_sessions_per_variant):
            session_id = str(uuid.uuid4())
            start_time = now - random.randint(0, 3600) * 1000
            duration = random.randint(8, 45) * 1000
            end_time = start_time + duration
            converted = 1 if random.random() < base_conversion else 0

            conn.execute(
                "INSERT INTO sessions (session_id, variant, viewport_width, "
                "start_time, end_time, converted, ended_by) VALUES (?,?,?,?,?,?,?)",
                (session_id, variant, 1440, start_time, end_time, converted, "click"),
            )

            # mousemove uzorci
            num_points = random.randint(30, 70)
            t = start_time
            for _ in range(num_points):
                x, y = random_point(REGIONS[variant])
                t += random.randint(150, 250)
                conn.execute(
                    "INSERT INTO events (session_id, event_type, x_percent, "
                    "y_percent, scroll_percent, timestamp) VALUES (?, 'mousemove', ?, ?, NULL, ?)",
                    (session_id, x, y, t),
                )

            # klik na CTA regiju na kraju
            cta_y = 0.88 if variant == "A" else 0.80
            conn.execute(
                "INSERT INTO events (session_id, event_type, x_percent, "
                "y_percent, scroll_percent, timestamp) VALUES (?, 'click', ?, ?, NULL, ?)",
                (session_id, random.uniform(0.42, 0.58), cta_y + random.uniform(-0.02, 0.02), end_time),
            )

    conn.commit()
    conn.close()
    print(f"Ubačeno {num_sessions_per_variant} testnih sesija po varijanti u {DB_PATH}")


if __name__ == "__main__":
    seed()