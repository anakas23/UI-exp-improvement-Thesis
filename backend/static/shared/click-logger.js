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

  function logClick(zone, x, y) {
    sendToBackend('/api/log-click', {
      session_id: sessionId,
      page_variant: pageVariant,
      zone: zone,
      x: x,
      y: y,
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
    });
    return totalTime;
  }

  // --- Event listeneri ---

  document.addEventListener('click', function (e) {
    const zoneEl = e.target.closest('[data-zone]');
    if (!zoneEl) return;

    const zone = zoneEl.dataset.zone;
    logClick(zone, e.clientX, e.clientY);

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

  window.addEventListener('DOMContentLoaded', function () {
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