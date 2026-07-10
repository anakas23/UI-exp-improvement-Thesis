# Heatmap Project - Backend (Faza 2)

## Pokretanje

```bash
cd backend
pip install -r requirements.txt
python app.py
```

Server kreće na `http://localhost:5000`. Otvori u browseru:

- http://localhost:5000/variant-a.html
- http://localhost:5000/variant-b.html
- http://localhost:5000/variant-c.html

**Važno:** stranice moraju biti otvorene preko ovog servera (http://localhost:5000/...),
ne direktno kao `file://` s diska - inače `fetch()` pozivi u `click-logger.js` nemaju
kamo poslati podatke.

Baza `heatmap.db` (SQLite) se automatski stvara u `backend/` folderu čim prvi put
pokreneš `python app.py`. Ne treba je ručno kreirati.

## Struktura baze

**raw_clicks** - jedan red po kliku
```
session_id, page_variant, zone, x, y, timestamp_ms
```

**sessions** - jedan red po sesiji (dovršenoj ili napuštenoj)
```
session_id, page_variant, total_time_on_page, task_success
```

## Izvoz podataka

Za Fazu 3 (heatmape) i Fazu 4 (ML dataset), izvezi podatke kao CSV:

- http://localhost:5000/api/export/raw-clicks.csv
- http://localhost:5000/api/export/sessions.csv

Isto se može i preko dugmadi u donjem desnom kutu svake stranice
("⬇ Klikovi CSV" / "⬇ Sesije CSV").

## Praćenje testiranja uživo

http://localhost:5000/api/stats vraća broj sesija/klikova po varijanti - korisno
da vidiš koliko ispitanika je već testiralo svaku varijantu dok skupljaš podatke.

## Dijeljenje s ispitanicima izvan lokalnog računala

Ako želiš da netko testira stranicu s drugog uređaja (ne samo tvog laptopa),
`localhost` neće raditi za njih - potrebno je ili:
- pokrenuti backend na pravom serveru/hostingu (npr. PythonAnywhere, Render, ili
  bilo koji VPS), ili
- privremeno probušiti lokalni port alatom poput `ngrok` (`ngrok http 5000`)

Za potrebe završnog rada, ngrok je najbrže rješenje ako trebaš prikupiti podatke
od nekoliko ljudi bez postavljanja pravog servera.