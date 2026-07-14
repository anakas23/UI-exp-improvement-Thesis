# Heatmap Project - Backend (Faza 2)

## Pokretanje

```bash
cd backend
pip install -r requirements.txt
python app.py
```

Server kreće na `http://localhost:5000`.

## Link za testere (VAŽNA PROMJENA)

Sad postoji **jedan link** koji dijeliš svima:

```
http://localhost:5000/
```
(ili `.../` na kraju tvog ngrok/LAN linka, vidi dolje)

Svaki **novi** posjetitelj (novi uređaj/browser bez prethodnog cookieja)
dobiva **nasumično** jednu od tri varijante, sa ~33% šanse za svaku. Ista
osoba, ako refresha stranicu, i dalje ostaje na svojoj dodijeljenoj
varijanti (pamti se preko cookieja) - dakle svaka osoba rješava točno
JEDNU varijantu, bez mogućnosti da slučajno vidi drugu.

Za tvoje vlastito testiranje pojedinačnih varijanti (npr. provjeru izgleda),
i dalje možeš direktno otvoriti:
- http://localhost:5000/variant-a.html
- http://localhost:5000/variant-b.html
- http://localhost:5000/variant-c.html

Ako želiš sam sebi resetirati dodjeljenu varijantu (da bi dobio/la novu
nasumičnu na `/`), otvori: http://localhost:5000/admin/reset-assignment

## Dev traka (izvoz CSV / reset)

Dugmad za izvoz CSV-a i "novu sesiju" su **sakrivena** od stvarnih testera -
prikazuju se samo ako na link dodaš `?dev=1`, npr:
```
http://localhost:5000/variant-a.html?dev=1
```
Obični link koji šalješ testerima (`http://.../`) ih ne prikazuje.

**Važno:** stranice moraju biti otvorene preko ovog servera (http://localhost:5000/...),
ne direktno kao `file://` s diska - inače `fetch()` pozivi u `click-logger.js` nemaju
kamo poslati podatke.

Baza `heatmap.db` (SQLite) se automatski stvara u `backend/` folderu čim prvi put
pokreneš `python app.py`. Ne treba je ručno kreirati.

## Struktura baze

**raw_clicks** - jedan red po kliku
```
session_id, page_variant, zone, x, y, page_width, page_height, timestamp_ms
```
`page_width`/`page_height` su dimenzije CIJELE stranice (ne samo vidljivog
dijela) u trenu klika - koriste se da se pozicija klika normalizira na
postotak (0-1) stranice, čime heatmape postaju usporedive bez obzira je li
tester bio na mobitelu ili velikom monitoru.

**sessions** - jedan red po sesiji (dovršenoj ili napuštenoj)
```
session_id, page_variant, total_time_on_page, task_success, attempt_number
```
`attempt_number` broji je li ovo bio nečiji 1., 2. ili 3. testirani layout u
istom browseru (relevantno samo ako je ista osoba nekad testirala više
varijanti zaredom prije uvođenja nasumične dodjele - kod novog sustava svaka
osoba testira samo jednu varijantu pa će ovo uglavnom biti 1).

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

`localhost` radi samo na tvom računalu - testeri na drugim uređajima ga ne mogu
otvoriti. Dvije opcije, ovisno o situaciji:

### Opcija 1 - testeri su na istoj WiFi mreži (npr. kod kuće, na faksu)

Najjednostavnije, bez ikakve prijave/instalacije dodatnih alata.

1. Pokreni server kao i prije: `python app.py`
2. Pronađi svoju lokalnu IP adresu:
   - **Windows:** otvori cmd, upiši `ipconfig`, potraži "IPv4 Address" (npr. `192.168.1.23`)
   - **Mac/Linux:** otvori terminal, upiši `ifconfig` (ili `ip addr`), potraži adresu koja počinje s `192.168.` ili `10.`
3. Pošalji testerima link oblika: `http://TVOJA_IP_ADRESA:5000/variant-a.html`
   (npr. `http://192.168.1.23:5000/variant-a.html`)
4. Testeri moraju biti spojeni na **istu WiFi mrežu** kao i tvoje računalo

Ako ne radi, provjeri da firewall na tvom računalu ne blokira port 5000 (na
Windowsu może zatražiti dopuštenje prvi put kad pokreneš `python app.py`).

### Opcija 2 - testeri su bilo gdje (drugi grad, druga mreža)

Treba jedan besplatan alat koji "probuši tunel" do tvog lokalnog servera:
[ngrok](https://ngrok.com/download)

1. Preuzmi ngrok i napravi besplatan račun (ngrok.com)
2. Poveži ngrok sa svojim računom (uputa se prikaže nakon registracije,
   otprilike: `ngrok config add-authtoken TVOJ_TOKEN`)
3. Pokreni svoj server kao i prije: `python app.py`
4. U novom terminalu pokreni: `ngrok http 5000`
5. Ngrok ispiše link oblika `https://nešto-random.ngrok-free.app`
6. Pošalji testerima: `https://nešto-random.ngrok-free.app/variant-a.html`

**Napomena:** besplatni ngrok link vrijedi samo dok ti imaš `ngrok http 5000`
pokrenut u terminalu - kad ga ugasiš, link prestaje raditi. Za jedno
poslijepodne prikupljanja podataka to je dovoljno.

**Sigurnosna napomena:** kad server dijeliš van svog računala (bilo LAN ili
ngrok), provjeri da je `debug=False` u `app.py` (već je tako podešeno) - Flaskov
debug mod inače izlaže interaktivnu konzolu koja bi nepoznatoj osobi omogućila
pokretanje koda na tvom računalu.