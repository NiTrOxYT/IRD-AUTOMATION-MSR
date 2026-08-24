// IRD Sync Automation Frontend Application Controller

let sitesList = [];
let ws = null;
let currentRunStatus = null;

document.addEventListener('DOMContentLoaded', () => {
  initTabs();
  initWebSocket();
  loadSites();
  loadSettings();
  loadHistory();
  bindEvents();
});

// TAB SWITCHING
function initTabs() {
  document.querySelectorAll('.nav-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.tab-page').forEach(p => p.classList.remove('active'));

      btn.classList.add('active');
      const tabId = btn.getAttribute('data-tab');
      document.getElementById(`tab-${tabId}`).classList.add('active');

      if (tabId === 'sites') loadSitesConfigTable();
      if (tabId === 'history') loadHistory();
      if (tabId === 'diagnostics') scanWindows();
    });
  });
}

// WEBSOCKET REAL-TIME CONNECTION
function initWebSocket() {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsUrl = `${protocol}//${window.location.host}/ws`;

  ws = new WebSocket(wsUrl);

  ws.onopen = () => {
    console.log("WebSocket connected.");
  };

  ws.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data);
      if (msg.type === 'log') {
        appendLogToTerminal(msg.data);
      } else if (msg.type === 'status') {
        updateAutomationStatusUI(msg.data);
      }
    } catch (e) {
      console.error("Error parsing WS message:", e);
    }
  };

  ws.onclose = () => {
    setTimeout(initWebSocket, 3000); // Auto reconnect
  };
}

function appendLogToTerminal(log) {
  const term = document.getElementById('terminal-log');
  if (!term) return;

  const row = document.createElement('div');
  let levelClass = 'log-info';
  if (log.level === 'WARNING' || log.level === 'WARN') levelClass = 'log-warn';
  if (log.level === 'ERROR' || log.level === 'CRITICAL') levelClass = 'log-error';

  row.className = `log-row ${levelClass}`;
  row.textContent = `${log.timestamp} | ${log.level} | ${log.message}`;

  term.appendChild(row);
  term.scrollTop = term.scrollHeight;
}

// AUTOMATION STATUS UI UPDATER
function updateAutomationStatusUI(statusData) {
  currentRunStatus = statusData;

  const isRunning = statusData.is_running;
  const btnStart = document.getElementById('btn-start-sync');
  const btnDry = document.getElementById('btn-dry-run');
  const btnStop = document.getElementById('btn-stop-automation');

  btnStart.disabled = isRunning;
  btnDry.disabled = isRunning;
  btnStop.disabled = !isRunning;

  document.getElementById('live-indicator').style.display = isRunning ? 'inline-block' : 'none';
  document.getElementById('current-op-title').textContent = isRunning ? `Running: ${statusData.operation}` : 'Ready for Synchronization';

  document.getElementById('progress-percentage-text').textContent = `${statusData.progress_percentage}%`;
  document.getElementById('progress-bar-fill').style.width = `${statusData.progress_percentage}%`;

  document.getElementById('banner-site-name').textContent = statusData.current_site_name || 'None';
  document.getElementById('banner-op-name').textContent = statusData.operation || 'Idle';
  document.getElementById('banner-status-detail').textContent = statusData.details || 'Ready to start';

  // If active site status changed, update queue row badge
  if (statusData.current_site_id) {
    const rowBadge = document.getElementById(`badge-queue-site-${statusData.current_site_id}`);
    if (rowBadge) {
      rowBadge.textContent = statusData.status;
      rowBadge.className = `status-badge ${getStatusBadgeClass(statusData.status)}`;
    }
  }

  if (statusData.reports_ready) {
    loadHistory();
  }
}

function getStatusBadgeClass(statusStr) {
  if (statusStr === 'NO ACTION POINT') return 'badge-no-action';
  if (statusStr === 'ACTION POINT FOUND') return 'badge-action-found';
  if (statusStr === 'FAILED') return 'badge-failed';
  if (statusStr === 'WAITING FOR SERVICE' || statusStr === 'RETRYING') return 'badge-recovering';
  if (statusStr === 'READY') return 'badge-ready';
  return 'badge-active';
}

// SITES DATA LOADING
async function loadSites() {
  try {
    const res = await fetch('/api/sites');
    sitesList = await res.json();
    renderQueueTable();
    updateMetricsSummary();
  } catch (e) {
    console.error("Failed loading sites:", e);
  }
}

function updateMetricsSummary() {
  document.getElementById('metric-total').textContent = sitesList.length;

  let noAction = 0, actionFound = 0, failed = 0, completed = 0;
  // Read counters from current queue state
  sitesList.forEach(s => {
    // defaults
  });

  document.getElementById('metric-completed').textContent = completed;
  document.getElementById('metric-processing').textContent = currentRunStatus && currentRunStatus.is_running ? 1 : 0;
  document.getElementById('metric-waiting').textContent = sitesList.filter(s => s.enabled).length;
}

// RENDER DASHBOARD SITES QUEUE
function renderQueueTable() {
  const tbody = document.getElementById('tbody-queue');
  tbody.innerHTML = '';

  sitesList.forEach(site => {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td><input type="checkbox" class="chk-site-queue" data-id="${site.id}" ${site.enabled ? 'checked' : ''}></td>
      <td style="font-weight: 600;">${escapeHtml(site.name)}</td>
      <td><code style="color: var(--accent-cyan);">${escapeHtml(site.launcher_button)}</code></td>
      <td><span class="status-badge badge-ready" id="badge-queue-site-${site.id}">READY</span></td>
      <td>
        <button class="btn-secondary btn-sm" onclick="testSingleSite(${site.id})">Test</button>
      </td>
    `;
    tbody.appendChild(tr);
  });

  updateSelectedCount();

  document.querySelectorAll('.chk-site-queue').forEach(chk => {
    chk.addEventListener('change', updateSelectedCount);
  });
}

function updateSelectedCount() {
  const selected = document.querySelectorAll('.chk-site-queue:checked').length;
  document.getElementById('queue-badge').textContent = `${selected} selected`;
}

// SITES CONFIG TAB TABLE
function loadSitesConfigTable() {
  const tbody = document.getElementById('tbody-sites-config');
  tbody.innerHTML = '';

  sitesList.forEach(site => {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td>${site.sort_order}</td>
      <td>
        <label class="switch">
          <input type="checkbox" onchange="toggleSiteEnabled(${site.id}, this.checked)" ${site.enabled ? 'checked' : ''}>
          <span class="slider"></span>
        </label>
      </td>
      <td style="font-weight: 600;">${escapeHtml(site.name)}</td>
      <td><code>${escapeHtml(site.launcher_button)}</code></td>
      <td>${escapeHtml(site.idp_username || '-')}</td>
      <td>${site.has_password ? '●●●●●●●●' : '<span style="color:var(--accent-amber);">Not Configured</span>'}</td>
      <td>
        <button class="btn btn-secondary btn-sm" onclick="openEditSiteModal(${site.id})">Edit</button>
        <button class="btn btn-danger btn-sm" onclick="deleteSiteClick(${site.id})">Delete</button>
        <button class="btn btn-info btn-sm" onclick="testSingleSite(${site.id})">Test</button>
      </td>
    `;
    tbody.appendChild(tr);
  });
}

// RUN AUTOMATION ACTIONS
async function startAutomation(dryRun = false) {
  const selectedIds = Array.from(document.querySelectorAll('.chk-site-queue:checked')).map(c => parseInt(c.getAttribute('data-id')));
  if (selectedIds.length === 0) {
    alert("Please select at least one site to process.");
    return;
  }

  try {
    const res = await fetch('/api/automation/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ site_ids: selectedIds, dry_run: dryRun })
    });
    const data = await res.json();
    if (!res.ok) alert(data.detail || "Failed starting automation.");
  } catch (e) {
    alert("Error starting automation: " + e.message);
  }
}

async function stopAutomation() {
  if (confirm("Are you sure you want to stop the current automation run?")) {
    await fetch('/api/automation/stop', { method: 'POST' });
  }
}

async function resumeAutomation() {
  try {
    const res = await fetch('/api/history');
    const runs = await res.json();
    if (runs.length === 0) {
      alert("No previous run found to resume.");
      return;
    }
    const lastRun = runs[0];
    await fetch('/api/automation/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ resume_run_id: lastRun.id })
    });
  } catch (e) {
    alert("Resume failed: " + e.message);
  }
}

async function testSingleSite(siteId) {
  alert(`Testing connection for site ID ${siteId}. Check execution terminal for live status.`);
  try {
    const res = await fetch(`/api/sites/${siteId}/test`, { method: 'POST' });
    const data = await res.json();
    alert(data.message);
  } catch (e) {
    alert("Test failed: " + e.message);
  }
}

// SITE MODAL & CRUD
function openAddSiteModal() {
  document.getElementById('modal-site-title').textContent = "Add New Site";
  document.getElementById('modal-site-id').value = "";
  document.getElementById('modal-site-name').value = "";
  document.getElementById('modal-site-button').value = "";
  document.getElementById('modal-site-url').value = "";
  document.getElementById('modal-site-username').value = "";
  document.getElementById('modal-site-password').value = "";
  document.getElementById('modal-site-order').value = sitesList.length + 1;
  document.getElementById('modal-site-enabled').checked = true;

  document.getElementById('modal-site').classList.add('active');
}

function openEditSiteModal(siteId) {
  const site = sitesList.find(s => s.id === siteId);
  if (!site) return;

  document.getElementById('modal-site-title').textContent = "Edit Site Configuration";
  document.getElementById('modal-site-id').value = site.id;
  document.getElementById('modal-site-name').value = site.name;
  document.getElementById('modal-site-button').value = site.launcher_button;
  document.getElementById('modal-site-url').value = site.url;
  document.getElementById('modal-site-username').value = site.idp_username;
  document.getElementById('modal-site-password').value = "";
  document.getElementById('modal-site-order').value = site.sort_order;
  document.getElementById('modal-site-enabled').checked = site.enabled;

  document.getElementById('modal-site').classList.add('active');
}

async function saveSiteModal() {
  const siteId = document.getElementById('modal-site-id').value;
  const payload = {
    name: document.getElementById('modal-site-name').value.trim(),
    launcher_button: document.getElementById('modal-site-button').value.trim(),
    url: document.getElementById('modal-site-url').value.trim(),
    idp_username: document.getElementById('modal-site-username').value.trim(),
    idp_password: document.getElementById('modal-site-password').value,
    sort_order: parseInt(document.getElementById('modal-site-order').value) || 0,
    enabled: document.getElementById('modal-site-enabled').checked
  };

  if (!payload.name || !payload.launcher_button) {
    alert("Site Name and Launcher Button are required.");
    return;
  }

  const url = siteId ? `/api/sites/${siteId}` : '/api/sites';
  const method = siteId ? 'PUT' : 'POST';

  try {
    const res = await fetch(url, {
      method: method,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    if (res.ok) {
      document.getElementById('modal-site').classList.remove('active');
      await loadSites();
      loadSitesConfigTable();
    } else {
      const err = await res.json();
      alert(err.detail || "Save failed.");
    }
  } catch (e) {
    alert("Error saving site: " + e.message);
  }
}

async function toggleSiteEnabled(siteId, isEnabled) {
  await fetch(`/api/sites/${siteId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ enabled: isEnabled })
  });
  await loadSites();
}

async function deleteSiteClick(siteId) {
  if (confirm("Are you sure you want to delete this site configuration?")) {
    await fetch(`/api/sites/${siteId}`, { method: 'DELETE' });
    await loadSites();
    loadSitesConfigTable();
  }
}

// HISTORY & REPORTS
async function loadHistory() {
  try {
    const res = await fetch('/api/history');
    const history = await res.json();
    const tbody = document.getElementById('tbody-history');
    tbody.innerHTML = '';

    history.forEach(r => {
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td style="font-weight: 600;">${r.run_date}</td>
        <td>${r.start_time}</td>
        <td>${r.end_time || 'In Progress'}</td>
        <td>${r.total_sites}</td>
        <td>${r.completed_sites}</td>
        <td><span style="color: var(--accent-amber); font-weight:700;">${r.action_points_count}</span></td>
        <td><span style="color: var(--accent-green); font-weight:700;">${r.no_action_points_count}</span></td>
        <td><span style="color: var(--accent-red); font-weight:700;">${r.failed_sites_count}</span></td>
        <td><span class="status-badge ${r.status === 'COMPLETED' ? 'badge-no-action' : 'badge-failed'}">${r.status}</span></td>
        <td>
          <button class="btn btn-secondary btn-sm" onclick="viewRunDetails(${r.id})">View Detail</button>
        </td>
      `;
      tbody.appendChild(tr);
    });
  } catch (e) {
    console.error("Failed loading history:", e);
  }
}

async function viewRunDetails(runId) {
  try {
    const res = await fetch(`/api/history/${runId}`);
    const details = await res.json();
    const modalBody = document.getElementById('modal-history-body');

    let html = `
      <div style="margin-bottom: 16px; font-size: 13px;">
        <strong>Run Date:</strong> ${details.run.run_date} | <strong>Total Sites:</strong> ${details.run.total_sites} |
        <span style="color:var(--accent-green);">No Action Point: ${details.run.no_action_points_count}</span> |
        <span style="color:var(--accent-amber);">Action Point Found: ${details.run.action_points_count}</span>
      </div>
      <table class="data-table">
        <thead>
          <tr>
            <th>Site</th>
            <th>Result Status</th>
            <th>CSV Line 3 Preview</th>
            <th>Duration</th>
            <th>Retries</th>
          </tr>
        </thead>
        <tbody>
    `;

    details.results.forEach(s => {
      html += `
        <tr>
          <td style="font-weight: 600;">${escapeHtml(s.site_name)}</td>
          <td><span class="status-badge ${getStatusBadgeClass(s.action_point_status)}">${s.action_point_status}</span></td>
          <td><code>${escapeHtml(s.third_line_text || '-')}</code></td>
          <td>${s.duration_seconds.toFixed(1)}s</td>
          <td>${s.retry_count}</td>
        </tr>
      `;
    });

    html += `</tbody></table>`;
    modalBody.innerHTML = html;
    document.getElementById('modal-history-detail').classList.add('active');
  } catch (e) {
    alert("Error loading run details: " + e.message);
  }
}

// SETTINGS TAB
async function loadSettings() {
  try {
    const res = await fetch('/api/settings');
    const settings = await res.json();

    document.getElementById('setting-launcher-exe').value = settings.launcher_exe_path || '';
    document.getElementById('setting-launcher-title').value = settings.launcher_window_title || '';
    document.getElementById('setting-browser-type').value = settings.browser_type || 'chromium';
    document.getElementById('setting-headless').checked = settings.headless === true || settings.headless === 'true';

    document.getElementById('setting-page-timeout').value = settings.page_load_timeout || 120;
    document.getElementById('setting-login-timeout').value = settings.login_timeout || 60;
    document.getElementById('setting-fetch-timeout').value = settings.fetch_menu_timeout || 600;
    document.getElementById('setting-process-timeout').value = settings.process_menu_timeout || 600;
    document.getElementById('setting-recovery-timeout').value = settings.service_recovery_timeout || 600;
    document.getElementById('setting-max-retries').value = settings.max_process_retries || 3;
  } catch (e) {
    console.error("Failed loading settings:", e);
  }
}

async function saveSettings() {
  const payload = {
    launcher_exe_path: document.getElementById('setting-launcher-exe').value.trim(),
    launcher_window_title: document.getElementById('setting-launcher-title').value.trim(),
    browser_type: document.getElementById('setting-browser-type').value,
    headless: document.getElementById('setting-headless').checked,
    page_load_timeout: parseInt(document.getElementById('setting-page-timeout').value),
    login_timeout: parseInt(document.getElementById('setting-login-timeout').value),
    fetch_menu_timeout: parseInt(document.getElementById('setting-fetch-timeout').value),
    process_menu_timeout: parseInt(document.getElementById('setting-process-timeout').value),
    service_recovery_timeout: parseInt(document.getElementById('setting-recovery-timeout').value),
    max_process_retries: parseInt(document.getElementById('setting-max-retries').value)
  };

  try {
    await fetch('/api/settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    alert("Settings saved successfully!");
  } catch (e) {
    alert("Save settings failed: " + e.message);
  }
}

// DIAGNOSTICS TAB
async function scanWindows() {
  const tbody = document.getElementById('tbody-diagnostics');
  tbody.innerHTML = '<tr><td colspan="4">Scanning active Windows windows and controls...</td></tr>';

  try {
    const res = await fetch('/api/diagnostics/windows');
    const windows = await res.json();
    tbody.innerHTML = '';

    windows.forEach(w => {
      const btnTexts = (w.buttons || []).map(b => b.text).join(', ');
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td><code>${w.hwnd}</code></td>
        <td>${escapeHtml(w.process_name)}</td>
        <td style="font-weight: 600;">${escapeHtml(w.title)}</td>
        <td style="font-size: 12px; color: var(--accent-cyan);">${escapeHtml(btnTexts || 'No buttons detected')}</td>
      `;
      tbody.appendChild(tr);
    });
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="4" style="color:var(--accent-red);">Scan failed: ${e.message}</td></tr>`;
  }
}

// BIND DOM EVENT HANDLERS
function bindEvents() {
  document.getElementById('btn-select-all').addEventListener('click', () => {
    document.querySelectorAll('.chk-site-queue').forEach(c => c.checked = true);
    updateSelectedCount();
  });

  document.getElementById('btn-clear-all').addEventListener('click', () => {
    document.querySelectorAll('.chk-site-queue').forEach(c => c.checked = false);
    updateSelectedCount();
  });

  document.getElementById('chk-queue-header').addEventListener('change', (e) => {
    document.querySelectorAll('.chk-site-queue').forEach(c => c.checked = e.target.checked);
    updateSelectedCount();
  });

  document.getElementById('btn-start-sync').addEventListener('click', () => startAutomation(false));
  document.getElementById('btn-dry-run').addEventListener('click', () => startAutomation(true));
  document.getElementById('btn-stop-automation').addEventListener('click', stopAutomation);
  document.getElementById('btn-resume-run').addEventListener('click', resumeAutomation);

  document.getElementById('btn-open-add-site-modal').addEventListener('click', openAddSiteModal);
  document.getElementById('btn-close-modal-site').addEventListener('click', () => document.getElementById('modal-site').classList.remove('active'));
  document.getElementById('btn-cancel-modal-site').addEventListener('click', () => document.getElementById('modal-site').classList.remove('active'));
  document.getElementById('btn-save-modal-site').addEventListener('click', saveSiteModal);

  document.getElementById('btn-close-modal-history').addEventListener('click', () => document.getElementById('modal-history-detail').classList.remove('active'));
  document.getElementById('btn-close-history-footer').addEventListener('click', () => document.getElementById('modal-history-detail').classList.remove('active'));

  document.getElementById('btn-save-settings').addEventListener('click', saveSettings);
  document.getElementById('btn-scan-windows').addEventListener('click', scanWindows);

  document.getElementById('btn-open-reports-folder').addEventListener('click', () => fetch('/api/open-folder/reports'));
  document.getElementById('btn-open-downloads-folder').addEventListener('click', () => fetch('/api/open-folder/downloads'));

  document.getElementById('btn-test-launcher').addEventListener('click', async () => {
    const res = await fetch('/api/launcher/test', { method: 'POST' });
    const data = await res.json();
    alert(data.message);
  });

  document.getElementById('btn-clear-terminal').addEventListener('click', () => {
    document.getElementById('terminal-log').innerHTML = '';
  });

  document.getElementById('btn-toggle-password').addEventListener('click', () => {
    const passInput = document.getElementById('modal-site-password');
    passInput.type = passInput.type === 'password' ? 'text' : 'password';
  });
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
