/**
 * click-logger.js
 * ----------------
 * Zajednička skripta za sve varijante stranice (A/B/C).
 * Bilježi klikove po zonama (data-zone atribut) i mjeri vrijeme
 * do dovršetka zadatka (klik na ciljani CTA gumb, data-task-target="true").
 *
 * TRENUTNO: podaci se spremaju u localStorage (radi testiranja bez backenda).
 * KASNIJE (Faza 3): appendItem() se može zamijeniti s fetch() pozivom
 * prema pravom backendu - ostatak koda se ne mijenja.
 *
 * Format sirovog klika:   {session_id, page_variant, zone, x, y, timestamp_ms}
 * Format sesijskog sažetka: {session_id, page_variant, total_time_on_page, task_success}
 */

(function () {
  const STORAGE_RAW = 'heatmap_raw_clicks';
  const STORAGE_SESSIONS = 'heatmap_sessions';

  // --- Pomoćne funkcije za localStorage ---

  function loadArray(key) {
    try {
      return JSON.parse(localStorage.getItem(key)) || [];
    } catch (e) {
      return [];
    }
  }

  function saveArray(key, arr) {
    localStorage.setItem(key, JSON.stringify(arr));
  }

  function appendItem(key, item) {
    const arr = loadArray(key);
    arr.push(item);
    saveArray(key, arr);
  }

  // --- Session identifikacija ---

  function getSessionId() {
    let id = sessionStorage.getItem('heatmap_session_id');
    if (!id) {
      id = 'sess_' + Date.now() + '_' + Math.random().toString(36).slice(2, 9);
      sessionStorage.setItem('heatmap_session_id', id);
    }
    return id;
  }

  const sessionId = getSessionId();
  const pageVariant = document.body.dataset.pageVariant || 'unknown';
  const startTime = Date.now();
  let taskCompleted = false;

  // --- Logiranje ---

  function logClick(zone, x, y) {
    appendItem(STORAGE_RAW, {
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
    appendItem(STORAGE_SESSIONS, {
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

  // --- Alat za izvoz podataka (za testiranje prije nego postoji backend) ---

  function downloadCSV(content, filename) {
    const blob = new Blob([content], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  }

  window.heatmapExportCSV = function () {
    const raw = loadArray(STORAGE_RAW);
    let csvRaw = 'session_id,page_variant,zone,x,y,timestamp_ms\n';
    raw.forEach((r) => {
      csvRaw += `${r.session_id},${r.page_variant},${r.zone},${r.x},${r.y},${r.timestamp_ms}\n`;
    });
    downloadCSV(csvRaw, 'raw_clicks.csv');

    const sessions = loadArray(STORAGE_SESSIONS);
    let csvSessions = 'session_id,page_variant,total_time_on_page,task_success\n';
    sessions.forEach((s) => {
      csvSessions += `${s.session_id},${s.page_variant},${s.total_time_on_page},${s.task_success}\n`;
    });
    downloadCSV(csvSessions, 'sessions.csv');
  };

  window.heatmapClearData = function () {
    localStorage.removeItem(STORAGE_RAW);
    localStorage.removeItem(STORAGE_SESSIONS);
    sessionStorage.removeItem('heatmap_session_id');
    alert('Svi lokalno spremljeni podaci su obrisani. Osvježite stranicu za novu sesiju.');
  };

  // --- Mala dev traka za izvoz/reset (ukloniti ili sakriti za pravo testiranje) ---

  window.addEventListener('DOMContentLoaded', function () {
    const bar = document.createElement('div');
    bar.className = 'hm-devbar';
    bar.innerHTML = `
      <button type="button" onclick="window.heatmapExportCSV()">⬇ Preuzmi CSV</button>
      <button type="button" onclick="window.heatmapClearData()">✕ Reset podataka</button>
    `;
    document.body.appendChild(bar);
  });
})();