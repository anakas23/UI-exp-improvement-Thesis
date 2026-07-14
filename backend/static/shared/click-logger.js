/**
 * click-logger.js
 * ----------------
 * Zajednička skripta za sve varijante stranice (A/B/C).
 * Bilježi klikove po zonama (data-zone atribut) i mjeri vrijeme
 * do dovršetka zadatka (klik na ciljani CTA gumb, data-task-target="true").
 *
 * Podaci se šalju na backend (Faza 2, Flask + SQLite) preko fetch()
 * poziva na /api/log-click i /api/log-session. Stranice MORAJU biti
 * poslužene s istog servera (http://localhost:5000/variant-a.html),
 * a ne otvorene direktno kao file:// - inače fetch nema kamo poslati podatke.
 *
 * Format sirovog klika:      {session_id, page_variant, zone, x, y, timestamp_ms}
 * Format sesijskog sažetka:  {session_id, page_variant, total_time_on_page, task_success}
 */

(function () {
  // --- Session identifikacija ---
  // VAŽNO: session_id se generira IZNOVA pri svakom učitavanju stranice,
  // bez čitanja/pisanja u sessionStorage. sessionStorage je vezan za tab
  // (ne za pojedinu stranicu), pa bi navigacija između variant-a/b/c.html
  // u istom tabu inače ponovno koristila STARI session_id iz prethodne
  // varijante - što razbija podatke (jedna "sesija" bi imala klikove s
  // dvije različite varijante). Svježa generacija po loadu jamči da
  // jedna sesija = točno jedan posjet točno jednoj varijanti.

  function generateSessionId() {
    return 'sess_' + Date.now() + '_' + Math.random().toString(36).slice(2, 9);
  }

  const sessionId = generateSessionId();
  const pageVariant = document.body.dataset.pageVariant || 'unknown';
  const startTime = Date.now();
  let taskCompleted = false;

  // --- Brojač redoslijeda pokušaja (za korekciju efekta učenja) ---
  // Za razliku od session_id (koji je nov za svaki page load), ovaj brojač
  // koristi localStorage (traje preko svih stranica/reloadova u istom
  // browseru) da zabilježi je li ovo nečiji 1., 2. ili 3. testirani layout
  // u ovoj "seansi" testiranja. Ako ista osoba testira sve 3 varijante
  // zaredom u istom browseru, treća varijanta dobiva attempt_number=3,
  // što kasnije omogućuje da se u analizi izdvoji SAMO attempt_number=1
  // za poštenu A/B/C usporedbu bez efekta učenja.
  //
  // Ograničenje: ovo je heuristika vezana za browser, ne za osobu - ako
  // netko testira na drugom uređaju/browseru ili obriše localStorage
  // između varijanti, brojač kreće ispočetka. Za većinu slučajeva
  // (ista osoba, isti laptop, sve u jednom sjedenju) dovoljno dobro radi.

  function getNextAttemptNumber() {
    const current = parseInt(localStorage.getItem('heatmap_attempt_count') || '0', 10);
    const next = current + 1;
    localStorage.setItem('heatmap_attempt_count', String(next));
    return next;
  }

  const attemptNumber = getNextAttemptNumber();

  // --- Slanje na backend ---
  // `keepalive: true` osigurava da fetch pokušaj dovrši i kad se poziva
  // iz 'beforeunload' handlera (korisnik zatvara/napušta stranicu).

  function sendToBackend(endpoint, payload) {
    fetch(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      keepalive: true,
    }).catch((err) => {
      console.error('Neuspjelo slanje podataka na backend:', endpoint, err);
    });
  }

  // --- Pozicija klika RELATIVNA na zonu (ispravka umjesto page_width/height) ---
  // Zašto: cijela visina stranice (document.scrollHeight) mijenja se
  // dinamički kako shop-flow.js otvara/zatvara popise i modale, pa isti
  // klik "na istom mjestu na ekranu" dobiva RAZLIČITU poziciju ovisno kad je
  // zabilježen. Rješenje: mjeri poziciju unutar granica SAME zone koja je
  // kliknuta (npr. "15% od lijevog ruba te zone") - neovisno o promjeni
  // visine stranice ili veličini ekrana.

  function getZoneContainerRect(zone) {
    // "cta" zona je gumb unutar dinamički stvorenog modala, nema stalni
    // ".zone-cta" kontejner - koristi modal-box umjesto toga.
    const selector = zone === 'cta' ? '.modal-box' : '.zone-' + zone;
    const container = document.querySelector(selector);
    return container ? container.getBoundingClientRect() : null;
  }

  function logClick(zone, pageX, pageY, zoneRelX, zoneRelY) {
    sendToBackend('/api/log-click', {
      session_id: sessionId,
      page_variant: pageVariant,
      zone: zone,
      x: pageX,
      y: pageY,
      zone_rel_x: zoneRelX,
      zone_rel_y: zoneRelY,
      timestamp_ms: Date.now(),
    });
  }

  function finalizeSession(success) {
    if (taskCompleted) return null;
    taskCompleted = true;
    const totalTime = (Date.now() - startTime) / 1000;
    sendToBackend('/api/log-session', {
      session_id: sessionId,
      page_variant: pageVariant,
      total_time_on_page: totalTime,
      task_success: success ? 1 : 0,
      attempt_number: attemptNumber,
    });
    return totalTime;
  }

  // --- Event listeneri ---

  document.addEventListener('click', function (e) {
    const zoneEl = e.target.closest('[data-zone]');
    if (!zoneEl) return;

    const zone = zoneEl.dataset.zone;

    const containerRect = getZoneContainerRect(zone);
    let zoneRelX = null;
    let zoneRelY = null;
    if (containerRect && containerRect.width > 0 && containerRect.height > 0) {
      zoneRelX = (e.clientX - containerRect.left) / containerRect.width;
      zoneRelY = (e.clientY - containerRect.top) / containerRect.height;
      zoneRelX = Math.min(1, Math.max(0, zoneRelX));
      zoneRelY = Math.min(1, Math.max(0, zoneRelY));
    }

    logClick(zone, e.pageX, e.pageY, zoneRelX, zoneRelY);

    if (zoneEl.dataset.taskTarget === 'true' && !taskCompleted) {
      const totalTime = finalizeSession(true);
      showCompletionOverlay(totalTime);
    }
  });

  window.addEventListener('beforeunload', function () {
    if (!taskCompleted) {
      finalizeSession(false);
    }
  });

  // --- UI: poruka o dovršetku zadatka ---

  function showCompletionOverlay(totalTime) {
    const overlay = document.createElement('div');
    overlay.className = 'modal-overlay';
    overlay.innerHTML = `
      <div class="modal-box">
        <h2>Hvala na sudjelovanju!</h2>
        <p>Zadatak je uspješno dovršen.</p>
        <p class="completion-time">Ukupno vrijeme: ${totalTime.toFixed(1)} s</p>
        <p class="completion-note">Rezultat je zabilježen za analizu.</p>
      </div>
    `;
    document.body.appendChild(overlay);
  }

  // --- Mala dev traka (izvoz preko backend endpointa / nova sesija) ---
  // Vidljiva SAMO tebi, kad na link dodaš ?dev=1 (npr. .../variant-a.html?dev=1).
  // Stvarni testeri koji otvore obični link je NE vide - ne treba im smetati
  // niti izgledati neprofesionalno na njihovom uređaju.

  window.addEventListener('DOMContentLoaded', function () {
    const isDevMode = new URLSearchParams(window.location.search).get('dev') === '1';
    if (!isDevMode) return;

    const bar = document.createElement('div');
    bar.className = 'hm-devbar';
    bar.innerHTML = `
      <button type="button" onclick="window.open('/api/export/raw-clicks.csv')">⬇ Klikovi CSV</button>
      <button type="button" onclick="window.open('/api/export/sessions.csv')">⬇ Sesije CSV</button>
      <button type="button" id="hmNewSession">↻ Reload / nova sesija</button>
    `;
    document.body.appendChild(bar);

    document.getElementById('hmNewSession').addEventListener('click', function () {
      location.reload();
    });
  });
})();