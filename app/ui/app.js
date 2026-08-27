// IRD Sync Automation Frontend Application Controller
// Version query cache-busting: app.js?v=phase7fix2

// --- GLOBAL FRONTEND ERROR CAPTURE ---
window.onerror = function(msg, url, lineNo, columnNo, error) {
  const cleanUrl = url ? url.split('/').pop() : 'app.js';
  const cleanMsg = `[UI ERROR] ${msg} (${cleanUrl}:${lineNo}:${columnNo})`;
  console.error(cleanMsg, error);

  const diagLog = document.getElementById('terminal-log');
  if (diagLog) {
    const row = document.createElement('div');
    row.className = 'log-row log-error';
    row.textContent = cleanMsg;
    diagLog.appendChild(row);
  }

  const uiBadge = document.getElementById('badge-ui-health');
  if (uiBadge) {
    uiBadge.textContent = 'UI: ERROR';
    uiBadge.className = 'status-badge badge-failed';
  }
  return false;
};

window.addEventListener('unhandledrejection', function(event) {
  console.error('[UI ERROR] Unhandled Promise Rejection:', event.reason);
});

// Global Click Listener Diagnostic (Prompt Section 6)
document.addEventListener("click", (event) => {
  const button = event.target.closest("button");
  if (button) {
    console.log("[UI CLICK]", button.id || "no-id", button.textContent.trim());
  }
});


// Global State Variables
let sitesList = [];
let ws = null;
let currentRunStatus = null;


// --- SAFE COMPONENT INITIALIZER HELPER ---
function safeInit(name, fn) {
  try {
    fn();
    console.log(`[UI INIT] ${name}: PASS`);
  } catch (e) {
    console.error(`[UI INIT ERROR] ${name}:`, e);
  }
}

// --- DIAGNOSTIC EVENT BINDING HELPERS ---
function bindClick(id, handler) {
  console.log(`[UI] Binding button: ${id}`);
  const el = document.getElementById(id);
  if (el) {
    console.log(`[UI] BUTTON BOUND: ${id}`);
    el.addEventListener('click', async (e) => {
      e.preventDefault();
      console.log(`[UI] BUTTON CLICKED: ${id}`);
      console.log(`[UI] HANDLER STARTED: ${handler.name || id}`);
      try {
        await handler(e);
        console.log(`[UI] HANDLER SUCCESS: ${handler.name || id}`);
      } catch (err) {
        console.error(`[UI] HANDLER FAILED: ${handler.name || id}`, err);
      }
    });
    return true;
  } else {
    console.warn(`[UI] MISSING BUTTON: ${id}`);
    return false;
  }
}

function bindEvent(id, eventType, handler) {
  const el = document.getElementById(id);
  if (el) {
    el.addEventListener(eventType, async (e) => {
      try {
        await handler(e);
      } catch (err) {
        console.error(`[UI EVENT ERROR] Error handling ${eventType} on #${id}:`, err);
      }
    });
    return true;
  } else {
    console.warn(`[UI BIND WARNING] Element #${id} not found.`);
    return false;
  }
}


// --- TAB NAVIGATION SYSTEM (Independent of Backend APIs) ---
function navigateToTab(tabId) {
  document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('.tab-page').forEach(p => p.classList.remove('active'));

  const targetNav = document.querySelector(`.nav-btn[data-tab="${tabId}"]`);
  if (targetNav) targetNav.classList.add('active');

  const targetTab = document.getElementById(`tab-${tabId}`);
  if (targetTab) {
    targetTab.classList.add('active');
    console.log(`[NAVIGATION] Switched to tab: ${tabId}`);
  } else {
    console.warn(`[NAVIGATION WARNING] Tab element #tab-${tabId} not found.`);
  }

  // Trigger lazy component loads on tab switch
  if (tabId === 'sites') safeInit('loadSitesConfigTable', loadSitesConfigTable);
  if (tabId === 'history') safeInit('loadHistory', loadHistory);
  if (tabId === 'settings') safeInit('loadSettingsTabs', () => { loadPuTTYInfo(); loadOfficeSshSettings(); loadGlobalTunnelSettings(); });
  if (tabId === 'diagnostics') safeInit('loadDiagnostics', () => { scanWindows(); loadPackageHealth(); });
}

function initNavigation() {
  document.querySelectorAll('.nav-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.preventDefault();
      const tabId = btn.getAttribute('data-tab');
      if (tabId) navigateToTab(tabId);
    });
  });
}

// Temporary diagnostic helper
window.testNavigation = function() {
  const tabs = ['dashboard', 'sites', 'history', 'integration-test', 'settings', 'diagnostics'];
  console.log("========================================");
  console.log("Navigation Diagnostics");
  console.log("========================================");
  tabs.forEach(t => {
    const btn = document.querySelector(`.nav-btn[data-tab="${t}"]`);
    const page = document.getElementById(`tab-${t}`);
    console.log(`${t.padEnd(18)} Button: ${btn ? 'FOUND' : 'MISSING'} | Tab: ${page ? 'FOUND' : 'MISSING'}`);
  });
  console.log("========================================");
  return "Navigation Diagnostics Complete";
};


// --- WEBSOCKET REAL-TIME CONNECTION ---
function updateWebSocketBadge(connected) {
  const badge = document.getElementById('badge-ws-status');
  if (!badge) return;
  if (connected) {
    badge.textContent = 'WebSocket: CONNECTED';
    badge.style.background = 'rgba(34, 197, 94, 0.2)';
    badge.style.color = '#4ade80';
  } else {
    badge.textContent = 'WebSocket: DISCONNECTED';
    badge.style.background = 'rgba(239, 68, 68, 0.2)';
    badge.style.color = '#f87171';
  }
}

function updateBackendBadge(connected) {
  const badge = document.getElementById('badge-backend-status');
  if (!badge) return;
  if (connected) {
    badge.textContent = 'Backend: CONNECTED';
    badge.style.background = 'rgba(59, 130, 246, 0.2)';
    badge.style.color = '#60a5fa';
  } else {
    badge.textContent = 'Backend: DISCONNECTED';
    badge.style.background = 'rgba(239, 68, 68, 0.2)';
    badge.style.color = '#f87171';
  }
}

function initWebSocket() {
  try {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws`;

    ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      console.log("WebSocket connected.");
      updateWebSocketBadge(true);
    };

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        if (msg.type === 'log') {
          appendLogToTerminal(msg.data);
          appendLogToTestConsole(msg.data);
        } else if (msg.type === 'status') {
          updateAutomationStatusUI(msg.data);
        }
      } catch (e) {
        console.error("Error parsing WS message:", e);
      }
    };

    ws.onclose = () => {
      updateWebSocketBadge(false);
      setTimeout(initWebSocket, 5000);
    };
    ws.onerror = (err) => {
      updateWebSocketBadge(false);
    };
  } catch (e) {
    console.warn("WebSocket init warning:", e);
    updateWebSocketBadge(false);
  }
}

function appendLogToTestConsole(log) {
  const liveLogs = document.getElementById('test-live-logs');
  if (!liveLogs) return;

  const row = document.createElement('div');
  let levelClass = 'log-info';
  if (log.level === 'WARNING' || log.level === 'WARN') levelClass = 'log-warn';
  if (log.level === 'ERROR' || log.level === 'CRITICAL') levelClass = 'log-error';

  row.className = `log-row ${levelClass}`;
  const timestamp = log.timestamp || new Date().toLocaleTimeString();
  row.textContent = `[${timestamp}] ${log.logger ? `[${log.logger}] ` : ''}${log.message}`;
  liveLogs.appendChild(row);
  liveLogs.scrollTop = liveLogs.scrollHeight;
}

function appendLogToTerminal(log) {
  const term = document.getElementById('terminal-log');
  if (!term) return;

  const row = document.createElement('div');
  let levelClass = 'log-info';
  if (log.level === 'WARNING' || log.level === 'WARN') levelClass = 'log-warn';
  if (log.level === 'ERROR' || log.level === 'CRITICAL') levelClass = 'log-error';

  row.className = `log-row ${levelClass}`;
  row.textContent = `${log.timestamp || new Date().toLocaleTimeString()} | ${log.level || 'INFO'} | ${log.message}`;

  term.appendChild(row);
  term.scrollTop = term.scrollHeight;
}


// --- AUTOMATION STATUS UI UPDATER ---
function updateAutomationStatusUI(statusData) {
  currentRunStatus = statusData;

  const isRunning = statusData.is_running;
  const btnStart = document.getElementById('btn-start-sync');
  const btnDry = document.getElementById('btn-dry-run');
  const btnStop = document.getElementById('btn-stop-automation');

  if (btnStart) btnStart.disabled = isRunning;
  if (btnDry) btnDry.disabled = isRunning;
  if (btnStop) btnStop.disabled = !isRunning;

  const ind = document.getElementById('live-indicator');
  if (ind) ind.style.display = isRunning ? 'inline-block' : 'none';

  const opTitle = document.getElementById('current-op-title');
  if (opTitle) opTitle.textContent = isRunning ? `Running: ${statusData.operation}` : 'Ready for Synchronization';

  const pText = document.getElementById('progress-percentage-text');
  if (pText) pText.textContent = `${statusData.progress_percentage}%`;

  const pFill = document.getElementById('progress-bar-fill');
  if (pFill) pFill.style.width = `${statusData.progress_percentage}%`;

  const bSite = document.getElementById('banner-site-name');
  if (bSite) bSite.textContent = statusData.current_site_name || 'None';

  const bOp = document.getElementById('banner-op-name');
  if (bOp) bOp.textContent = statusData.operation || 'Idle';

  const bIp = document.getElementById('banner-site-ip');
  if (bIp) bIp.textContent = statusData.current_site_ip || 'N/A';

  const bPort = document.getElementById('banner-site-port');
  if (bPort) bPort.textContent = statusData.current_site_port || 'N/A';

  const bLocalPort = document.getElementById('banner-local-port');
  if (bLocalPort) bLocalPort.textContent = statusData.current_local_port || 'N/A';

  const bUrl = document.getElementById('banner-url');
  if (bUrl) bUrl.textContent = statusData.current_url || 'N/A';


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


// --- SITES DATA LOADING ---
async function loadSites() {
  try {
    const res = await fetch('/api/sites');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    sitesList = await res.json();
    updateBackendBadge(true);
    renderQueueTable();
    populateTestSiteDropdown();
    updateMetricsSummary();
  } catch (e) {
    updateBackendBadge(false);
    console.error("Failed loading sites:", e);
  }
}

function populateTestSiteDropdown() {
  const sel = document.getElementById('select-test-site');
  if (!sel) return;
  sel.innerHTML = '';
  sitesList.forEach(s => {
    const opt = document.createElement('option');
    opt.value = s.id;
    opt.textContent = `${s.name} (${s.launcher_button || 'Site ' + s.id})`;
    sel.appendChild(opt);
  });
}

function updateMetricsSummary() {
  const totalEl = document.getElementById('metric-total');
  if (totalEl) totalEl.textContent = sitesList.length;

  let completed = 0;
  const compEl = document.getElementById('metric-completed');
  if (compEl) compEl.textContent = completed;

  const procEl = document.getElementById('metric-processing');
  if (procEl) procEl.textContent = currentRunStatus && currentRunStatus.is_running ? 1 : 0;

  const waitEl = document.getElementById('metric-waiting');
  if (waitEl) waitEl.textContent = sitesList.filter(s => s.enabled).length;
}

function renderQueueTable() {
  const tbody = document.getElementById('tbody-queue');
  if (!tbody) return;
  tbody.innerHTML = '';

  sitesList.forEach(site => {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td><input type="checkbox" class="chk-site-queue" data-id="${site.id}" ${site.enabled ? 'checked' : ''}></td>
      <td style="font-weight: 600;">${escapeHtml(site.name)}</td>
      <td><code style="color: var(--accent-cyan);">${escapeHtml(site.launcher_button || 'Site ' + site.id)}</code></td>
      <td><span class="status-badge badge-ready" id="badge-queue-site-${site.id}">READY</span></td>
      <td>
        <button class="btn-secondary btn-sm" type="button" onclick="testSingleSite(${site.id})">Test</button>
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
  const badge = document.getElementById('queue-badge');
  if (badge) badge.textContent = `${selected} selected`;
}


// --- SITES CONFIG TAB TABLE ---
function loadSitesConfigTable() {
  const tbody = document.getElementById('tbody-sites-config');
  if (!tbody) return;
  tbody.innerHTML = '';

  sitesList.forEach(site => {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td>${site.id}</td>
      <td style="font-weight: 600; color: #f8fafc;">${escapeHtml(site.name)}</td>
      <td><code style="color: #4ade80;">${escapeHtml(site.site_ip || '10.x.x.x')}</code></td>
      <td><code>${site.site_port || 80}</code></td>
      <td><code>${site.local_port || 18001}</code></td>
      <td>${escapeHtml(site.idp_username || 'None')}</td>
      <td><span class="status-badge ${site.enabled ? 'badge-no-action' : 'badge-failed'}">${site.enabled ? 'ENABLED' : 'DISABLED'}</span></td>
      <td>
        <button class="btn btn-secondary btn-sm" type="button" onclick="openEditSiteModal(${site.id})">Edit</button>
        <button class="btn btn-danger btn-sm" type="button" onclick="deleteSiteClick(${site.id})">Delete</button>
      </td>
    `;
    tbody.appendChild(tr);
  });
}

function openAddSiteModal() {
  document.getElementById('modal-site-title').textContent = "Add New Site";
  document.getElementById('modal-site-id').value = "";
  document.getElementById('modal-site-name').value = "";
  document.getElementById('modal-site-ip').value = "";
  document.getElementById('modal-site-port').value = 80;

  const nextPort = 18001 + sitesList.length;
  document.getElementById('modal-site-local-port').value = nextPort;
  document.getElementById('modal-site-order').value = sitesList.length + 1;
  document.getElementById('modal-site-username').value = "";
  document.getElementById('modal-site-password').value = "";
  document.getElementById('modal-site-enabled').checked = true;

  document.getElementById('modal-site').classList.add('active');
}

function openEditSiteModal(siteId) {
  const site = sitesList.find(s => s.id === siteId);
  if (!site) return;

  document.getElementById('modal-site-title').textContent = `Edit Site #${site.id}`;
  document.getElementById('modal-site-id').value = site.id;
  document.getElementById('modal-site-name').value = site.name;
  document.getElementById('modal-site-ip').value = site.site_ip || "";
  document.getElementById('modal-site-port').value = site.site_port || 80;
  document.getElementById('modal-site-local-port').value = site.local_port || 18001;
  document.getElementById('modal-site-order').value = site.sort_order || 0;
  document.getElementById('modal-site-username').value = site.idp_username || "";
  document.getElementById('modal-site-password').value = "";
  document.getElementById('modal-site-enabled').checked = site.enabled;

  document.getElementById('modal-site').classList.add('active');
}

async function saveSiteModal() {
  const siteId = document.getElementById('modal-site-id').value;
  const payload = {
    name: document.getElementById('modal-site-name').value.trim(),
    site_ip: document.getElementById('modal-site-ip').value.trim(),
    site_port: parseInt(document.getElementById('modal-site-port').value, 10) || 80,
    local_port: parseInt(document.getElementById('modal-site-local-port').value, 10) || 18001,
    sort_order: parseInt(document.getElementById('modal-site-order').value, 10) || 0,
    idp_username: document.getElementById('modal-site-username').value.trim(),
    idp_password: document.getElementById('modal-site-password').value,
    enabled: document.getElementById('modal-site-enabled').checked
  };

  if (!payload.name) {
    alert("Site Name is required.");
    return;
  }

  try {
    let res;
    if (siteId) {
      res = await fetch(`/api/sites/${siteId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
    } else {
      res = await fetch('/api/sites', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
    }

    if (res.ok) {
      document.getElementById('modal-site').classList.remove('active');
      await loadSites();
      loadSitesConfigTable();
    } else {
      const err = await res.json();
      alert(`Error saving site: ${err.detail || res.statusText}`);
    }
  } catch (e) {
    alert("Error saving site: " + e.message);
  }
}


async function deleteSiteClick(siteId) {
  if (!confirm(`Are you sure you want to delete Site #${siteId}?`)) return;
  try {
    const res = await fetch(`/api/sites/${siteId}`, { method: 'DELETE' });
    if (res.ok) {
      await loadSites();
      loadSitesConfigTable();
    } else {
      alert("Failed to delete site.");
    }
  } catch (e) {
    alert("Error deleting site: " + e.message);
  }
}


// --- AUTOMATION CONTROL FUNCTIONS ---
async function startAutomation(isDryRun) {
  const selectedIds = Array.from(document.querySelectorAll('.chk-site-queue:checked')).map(c => parseInt(c.getAttribute('data-id')));
  if (selectedIds.length === 0) {
    alert("Please select at least one site.");
    return;
  }

  try {
    const endpoint = isDryRun ? '/api/automation/start-dry-run' : '/api/automation/start-sync';
    const res = await fetch(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ site_ids: selectedIds })
    });
    if (!res.ok) {
      const err = await res.json();
      alert(`Error starting automation: ${err.detail || res.statusText}`);
    }
  } catch (e) {
    alert("Failed to send start command: " + e.message);
  }
}

async function stopAutomation() {
  try {
    await fetch('/api/automation/stop', { method: 'POST' });
  } catch (e) {
    alert("Error stopping automation: " + e.message);
  }
}

async function resumeAutomation() {
  try {
    await fetch('/api/automation/resume', { method: 'POST' });
  } catch (e) {
    alert("Error resuming automation: " + e.message);
  }
}


// --- RUN HISTORY TAB ---
async function loadHistory() {
  const tbody = document.getElementById('tbody-history');
  if (!tbody) return;

  try {
    const res = await fetch('/api/runs');
    if (!res.ok) return;
    const runs = await res.json();
    tbody.innerHTML = '';

    runs.forEach(r => {
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td>#${r.id}</td>
        <td>${r.run_date}</td>
        <td>${r.start_time}</td>
        <td>${r.end_time || 'Running...'}</td>
        <td><span class="status-badge ${r.status === 'COMPLETED' ? 'badge-no-action' : (r.status === 'FAILED' ? 'badge-failed' : 'badge-active')}">${r.status}</span></td>
        <td>${r.completed_sites} / ${r.total_sites}</td>
        <td><strong style="color: var(--accent-amber);">${r.action_points_count}</strong></td>
        <td>
          <button class="btn btn-secondary btn-sm" type="button" onclick="viewHistoryDetail(${r.id})">Details</button>
        </td>
      `;
      tbody.appendChild(tr);
    });
  } catch (e) {
    console.error("Failed loading history:", e);
  }
}

async function viewHistoryDetail(runId) {
  const modal = document.getElementById('modal-history-detail');
  const body = document.getElementById('modal-history-body');
  if (!modal || !body) return;

  body.innerHTML = '<div style="color:#94a3b8;">Loading run details...</div>';
  modal.classList.add('active');

  try {
    const res = await fetch(`/api/runs/${runId}`);
    const data = await res.json();

    let html = `
      <div style="margin-bottom: 16px; font-size: 0.9rem;">
        <strong>Run #${data.run.id}</strong> | Date: ${data.run.run_date} | Status: <span class="status-badge badge-ready">${data.run.status}</span>
      </div>
      <table class="data-table">
        <thead>
          <tr>
            <th>Site Name</th>
            <th>Status</th>
            <th>Action Points</th>
            <th>CSV Path</th>
          </tr>
        </thead>
        <tbody>
    `;

    (data.results || []).forEach(r => {
      html += `
        <tr>
          <td>${escapeHtml(r.site_name)}</td>
          <td><span class="status-badge ${r.status === 'COMPLETED' ? 'badge-ready' : 'badge-failed'}">${r.status}</span></td>
          <td>${escapeHtml(r.action_point_status)}</td>
          <td><code>${escapeHtml(r.csv_path || 'N/A')}</code></td>
        </tr>
      `;
    });

    html += '</tbody></table>';
    body.innerHTML = html;
  } catch (e) {
    body.innerHTML = `<div style="color:#f87171;">Failed loading run details: ${e.message}</div>`;
  }
}


// --- SETTINGS TAB ---
async function loadSettings() {
  try {
    const res = await fetch('/api/settings');
    if (!res.ok) return;
    const s = await res.json();

    if (document.getElementById('setting-launcher-exe')) document.getElementById('setting-launcher-exe').value = s.launcher_exe_path || '';
    if (document.getElementById('setting-launcher-title')) document.getElementById('setting-launcher-title').value = s.launcher_window_title || '';
    if (document.getElementById('setting-browser-type')) document.getElementById('setting-browser-type').value = s.browser_type || 'chromium';
    if (document.getElementById('setting-headless')) document.getElementById('setting-headless').checked = bool(s.headless);
    if (document.getElementById('setting-putty-path')) document.getElementById('setting-putty-path').value = s.putty_path || '';

    if (document.getElementById('setting-default-local-port')) document.getElementById('setting-default-local-port').value = s.default_local_port || 18001;
    if (document.getElementById('setting-tunnel-timeout')) document.getElementById('setting-tunnel-timeout').value = s.tunnel_start_timeout || 30;
    if (document.getElementById('setting-auto-stop-tunnel')) document.getElementById('setting-auto-stop-tunnel').checked = bool(s.auto_stop_tunnel);
    if (document.getElementById('setting-auto-restart-tunnel')) document.getElementById('setting-auto-restart-tunnel').checked = bool(s.auto_restart_tunnel);

    if (document.getElementById('setting-page-timeout')) document.getElementById('setting-page-timeout').value = s.page_load_timeout || 60;
    if (document.getElementById('setting-login-timeout')) document.getElementById('setting-login-timeout').value = s.login_timeout || 60;
    if (document.getElementById('setting-fetch-timeout')) document.getElementById('setting-fetch-timeout').value = s.fetch_menu_timeout || 600;
    if (document.getElementById('setting-process-timeout')) document.getElementById('setting-process-timeout').value = s.process_menu_timeout || 600;
    if (document.getElementById('setting-recovery-timeout')) document.getElementById('setting-recovery-timeout').value = s.service_recovery_timeout || 600;
    if (document.getElementById('setting-max-retries')) document.getElementById('setting-max-retries').value = s.max_process_retries || 3;
  } catch (e) {
    console.error("Failed loading settings:", e);
  }
}

function bool(val) {
  if (typeof val === 'boolean') return val;
  if (typeof val === 'string') return val.toLowerCase() === 'true' || val === '1';
  return Boolean(val);
}

async function saveSettings() {
  const payload = {
    launcher_exe_path: document.getElementById('setting-launcher-exe').value.trim(),
    launcher_window_title: document.getElementById('setting-launcher-title').value.trim(),
    browser_type: document.getElementById('setting-browser-type').value,
    headless: document.getElementById('setting-headless').checked,
    putty_path: document.getElementById('setting-putty-path').value.trim(),
    default_local_port: parseInt(document.getElementById('setting-default-local-port').value) || 18001,
    tunnel_start_timeout: parseInt(document.getElementById('setting-tunnel-timeout').value) || 30,
    auto_stop_tunnel: document.getElementById('setting-auto-stop-tunnel').checked,
    auto_restart_tunnel: document.getElementById('setting-auto-restart-tunnel').checked,
    page_load_timeout: parseInt(document.getElementById('setting-page-timeout').value) || 60,
    login_timeout: parseInt(document.getElementById('setting-login-timeout').value) || 60,
    fetch_menu_timeout: parseInt(document.getElementById('setting-fetch-timeout').value) || 600,
    process_menu_timeout: parseInt(document.getElementById('setting-process-timeout').value) || 600,
    service_recovery_timeout: parseInt(document.getElementById('setting-recovery-timeout').value) || 600,
    max_process_retries: parseInt(document.getElementById('setting-max-retries').value) || 3
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

async function detectPuTTYExecutable() {
  try {
    const res = await fetch('/api/tunnel/detect', { method: 'POST' });
    const data = await res.json();
    if (data.plink) {
      document.getElementById('setting-putty-path').value = data.plink;
      alert(`PuTTY/Plink detected successfully at:\n${data.plink}`);
    } else {
      alert("Plink executable was not found automatically. Please specify path manually.");
    }
  } catch (e) {
    alert("Detection failed: " + e.message);
  }
}

async function loadPuTTYInfo() {
  try {
    const res = await fetch('/api/tunnel/info');
    if (!res.ok) return;
    const data = await res.json();

    const badgeStatus = document.getElementById('badge-plink-status');
    const badgeVersion = document.getElementById('badge-plink-version');

    if (badgeStatus) {
      if (data.found) {
        badgeStatus.textContent = `✓ ${data.relative_plink || 'FOUND'}`;
        badgeStatus.style.background = 'rgba(34, 197, 94, 0.2)';
        badgeStatus.style.color = '#4ade80';
        if (badgeVersion) badgeVersion.textContent = data.version || 'Release 0.85';
      } else {
        badgeStatus.textContent = '✕ PLINK NOT FOUND';
        badgeStatus.style.background = 'rgba(239, 68, 68, 0.2)';
        badgeStatus.style.color = '#f87171';
        if (badgeVersion) badgeVersion.textContent = 'Expected: tools/putty/plink.exe';
      }
    }
  } catch (e) {
    console.error("Failed loading PuTTY info:", e);
  }
}

async function testPlinkClick() {
  try {
    const res = await fetch('/api/tunnel/test-plink', { method: 'POST' });
    const data = await res.json();
    alert(`PLINK TEST RESULT:\n\nExecutable Path:\n${data.path}\n\nVersion Output:\n${data.version}\n\nResult: ${data.success ? 'PASS' : 'FAIL'}`);
  } catch (e) {
    alert("Plink test failed: " + e.message);
  }
}


// --- INTEGRATION TEST CONSOLE & HANDLERS ---
function initIntegrationTest() {
  console.log("[UI] Integration Test initialization started");

  const itButtons = [
    'btn-test-ui', 'btn-run-stage-test', 'btn-fnb-start-test',
    'btn-fnb-open-webpage', 'btn-fnb-test-playwright', 'btn-fnb-run-login-workflow',
    'btn-fnb-run-fetch-workflow', 'btn-fnb-run-fetch-test', 'btn-fnb-stop-tunnel',
    'btn-fnb-restart-tunnel'
  ];

  let foundCount = 0;
  let boundCount = 0;

  itButtons.forEach(id => {
    const el = document.getElementById(id);
    if (el) {
      foundCount++;
      if (!el.disabled) boundCount++;
    }
  });

  // Bind Integration Test Buttons explicitly
  bindClick('btn-test-ui', testUiButtonClick);
  bindClick('btn-run-stage-test', runStageTestUI);
  bindClick('btn-fnb-start-test', runFnbTunnelTestUI);
  bindClick('btn-fnb-open-webpage', openFnbWebpageTestUI);
  bindClick('btn-fnb-test-playwright', testPlaywrightTunnelUI);
  bindClick('btn-fnb-run-login-workflow', runFnbLoginWorkflowUI);
  bindClick('btn-fnb-run-fetch-workflow', runFnbFetchWorkflowUI);
  bindClick('btn-fnb-run-fetch-test', runFnbFetchWorkflowUI);
  bindClick('btn-fnb-stop-tunnel', stopFnbTunnelUI);
  bindClick('btn-fnb-restart-tunnel', restartFnbTunnelUI);
  bindClick('btn-test-remote-connectivity', runRemoteConnectivityTestUI);


  // Update UI Health Panel
  const foundEl = document.getElementById('it-health-found');
  if (foundEl) foundEl.textContent = `${foundCount} / 10`;

  const boundEl = document.getElementById('it-health-bound');
  if (boundEl) boundEl.textContent = `${boundCount} / 10`;

  console.log("[UI] Integration Test initialization completed");
}

async function testUiButtonClick() {
  console.log("[UI] TEST UI BUTTON CLICKED");
  const liveLogs = document.getElementById('fnb-live-logs');
  const outputBox = document.getElementById('test-output-box');

  const msg = `[${new Date().toLocaleTimeString()}] UI BUTTON TEST: PASS (Frontend click event wiring verified successfully)`;

  if (liveLogs) {
    liveLogs.innerHTML += `<div class="log-row log-info" style="color: #4ade80; font-weight: 700;">✓ ${escapeHtml(msg)}</div>`;
    liveLogs.scrollTop = liveLogs.scrollHeight;
  }
  if (outputBox) {
    outputBox.innerHTML = `<div class="log-row log-info" style="color: #4ade80; font-weight: 700;">✓ ${escapeHtml(msg)}</div>`;
  }

  alert("UI BUTTON TEST: PASS\nIntegration Test button events are working.");
}

async function runStageTestUI() {
  const selSite = document.getElementById('select-test-site');
  const selStage = document.getElementById('select-test-stage');
  const outputBox = document.getElementById('test-output-box');
  const liveLogs = document.getElementById('fnb-live-logs');

  const siteId = selSite ? parseInt(selSite.value) || 1 : 1;
  const stageKey = selStage ? selStage.value : 'backend_test';

  if (outputBox) {
    outputBox.innerHTML = `<div class="log-row log-info">[${new Date().toLocaleTimeString()}] Executing Stage Test: '${stageKey}' for Site ID #${siteId}...</div>`;
  }
  if (liveLogs) {
    liveLogs.innerHTML += `<div class="log-row log-info">[${new Date().toLocaleTimeString()}] Executing Stage Test: '${stageKey}'...</div>`;
    liveLogs.scrollTop = liveLogs.scrollHeight;
  }

  try {
    const res = await fetch('/api/diagnostics/stage-test', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ site_id: siteId, stage_key: stageKey })
    });
    const data = await res.json();

    if (data.logs && data.logs.length > 0) {
      const htmlLogs = data.logs.map(l => `<div class="log-row ${l.includes('ERROR') ? 'log-error' : 'log-info'}">${escapeHtml(l)}</div>`).join('');
      if (outputBox) outputBox.innerHTML = htmlLogs;
      if (liveLogs) {
        liveLogs.innerHTML += htmlLogs;
        liveLogs.scrollTop = liveLogs.scrollHeight;
      }
    } else if (outputBox) {
      outputBox.innerHTML = `<div class="log-row ${data.success ? 'log-info' : 'log-error'}">Stage '${stageKey}' Result: ${data.result}</div>`;
    }
  } catch (e) {
    if (outputBox) outputBox.innerHTML = `<div class="log-row log-error">Stage Test Request Error: ${escapeHtml(e.message)}</div>`;
  }
}

async function loadFnbTunnelValidationData() {
  try {
    const res = await fetch('/api/fnb-tunnel/config');
    if (!res.ok) return;
    const cfg = await res.json();

    if (document.getElementById('fnb-cfg-site-ip')) document.getElementById('fnb-cfg-site-ip').textContent = cfg.site_ip || '10.10.50.15';
    if (document.getElementById('fnb-cfg-ssh-host')) document.getElementById('fnb-cfg-ssh-host').textContent = `${cfg.ssh_host}:${cfg.ssh_port}`;
    if (document.getElementById('fnb-cfg-local-port')) document.getElementById('fnb-cfg-local-port').textContent = cfg.local_port || 18001;
    if (document.getElementById('fnb-cfg-web-url')) document.getElementById('fnb-cfg-web-url').textContent = cfg.web_url || `http://localhost:${cfg.local_port || 58430}/zmp/main-menu.do`;


    await refreshFnbTunnelStatus();
    await refreshFnbDiagnosticCommand();
  } catch (e) {
    console.error("Error loading FNB Tunnel Validation Data:", e);
  }
}

async function refreshFnbTunnelStatus() {
  try {
    const res = await fetch('/api/fnb-tunnel/status');
    if (!res.ok) return;
    const st = await res.json();

    const badge = document.getElementById('fnb-status-badge');
    if (badge) {
      badge.textContent = st.status;
      if (st.status === 'CONNECTED' || st.status === 'RUNNING') {
        badge.style.background = 'rgba(34, 197, 94, 0.2)';
        badge.style.color = '#4ade80';
      } else if (st.status === 'STARTING' || st.status === 'CONNECTING') {
        badge.style.background = 'rgba(234, 179, 8, 0.2)';
        badge.style.color = '#facc15';
      } else {
        badge.style.background = 'rgba(148, 163, 184, 0.2)';
        badge.style.color = '#94a3b8';
      }
    }

    if (document.getElementById('fnb-status-pid')) document.getElementById('fnb-status-pid').textContent = st.pid || 'N/A';
  } catch (e) {
    console.error("Error refreshing FNB status:", e);
  }
}

async function refreshFnbDiagnosticCommand() {
  try {
    const res = await fetch('/api/fnb-tunnel/command');
    if (!res.ok) return;
    const data = await res.json();
    const cmdEl = document.getElementById('fnb-diagnostic-cmd');
    if (cmdEl) cmdEl.textContent = data.command || 'NOT GENERATED';
  } catch (e) {
    console.error("Error fetching FNB command:", e);
  }
}

async function runRemoteConnectivityTestUI() {
  const banner = document.getElementById('fnb-feedback-banner');
  const liveLogs = document.getElementById('fnb-live-logs');
  const summary = document.getElementById('fnb-formatted-summary');

  if (banner) {
    banner.style.display = 'block';
    banner.textContent = 'OFFICE → SITE REMOTE CONNECTIVITY TEST STARTED';
    banner.style.background = 'rgba(245, 158, 11, 0.2)';
    banner.style.color = '#fbbf24';
  }

  if (summary) {
    summary.textContent = `============================================\n\nOFFICE → SITE NETWORK TEST\n\nSTATUS: RUNNING...\n\n============================================`;
  }

  try {
    const res = await fetch('/api/sites/22/remote-connectivity-test', { method: 'POST' });
    const data = await res.json();

    if (liveLogs && data.logs) {
      liveLogs.innerHTML = data.logs.map(l => `<div class="log-row ${l.includes('ERROR') ? 'log-error' : 'log-info'}">${escapeHtml(l)}</div>`).join('');
      liveLogs.scrollTop = liveLogs.scrollHeight;
    }

    if (summary) {
      summary.textContent = data.formatted_summary || `Result: ${data.failure_code}`;
      summary.style.color = data.success ? '#4ade80' : '#f87171';
    }

    if (banner) {
      banner.textContent = `OFFICE → SITE TEST FINISHED - TCP RESULT: ${data.remote_tcp}`;
      banner.style.background = data.success ? 'rgba(34, 197, 94, 0.2)' : 'rgba(239, 68, 68, 0.2)';
      banner.style.color = data.success ? '#4ade80' : '#f87171';
    }
  } catch (e) {
    if (banner) banner.textContent = `REMOTE TEST ERROR: ${e.message}`;
  }
}

async function runFnbTunnelTestUI() {

  const banner = document.getElementById('fnb-feedback-banner');
  const liveLogs = document.getElementById('fnb-live-logs');
  const summary = document.getElementById('fnb-formatted-summary');
  const chkKeep = document.getElementById('chk-keep-tunnel-running');

  if (banner) {
    banner.style.display = 'block';
    banner.textContent = 'PHASE 5E REAL FNB ENDPOINT VALIDATION STARTED';
    banner.style.background = 'rgba(59, 130, 246, 0.15)';
    banner.style.color = '#60a5fa';
  }

  if (liveLogs) {
    liveLogs.innerHTML = `
      <div class="log-row log-info">[${new Date().toLocaleTimeString()}] | INFO | [FNB] REAL FNB ENDPOINT VALIDATION STARTED</div>
    `;
  }

  if (summary) {
    summary.textContent = `========================================\n\nPHASE 5E — REAL FNB ENDPOINT VALIDATION\n\nSTATUS: RUNNING...\n\n========================================`;
  }

  try {
    const res = await fetch('/api/fnb-tunnel/test', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ keep_running: chkKeep ? chkKeep.checked : true })
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`);

    const data = await res.json();

    if (liveLogs && data.logs) {
      liveLogs.innerHTML = data.logs.map(l => `<div class="log-row ${l.includes('ERROR') ? 'log-error' : 'log-info'}">${escapeHtml(l)}</div>`).join('');
      liveLogs.scrollTop = liveLogs.scrollHeight;
    }

    if (summary) {
      summary.textContent = data.formatted_summary || 'No summary generated.';
      summary.style.color = data.result_status === 'REAL FNB TUNNEL — PASS' ? '#4ade80' : '#f87171';
    }

    if (banner) {
      banner.textContent = `FNB ENDPOINT VALIDATION RESULT: ${data.result_status}`;
      banner.style.background = data.result_status === 'REAL FNB TUNNEL — PASS' ? 'rgba(34, 197, 94, 0.2)' : 'rgba(239, 68, 68, 0.2)';
      banner.style.color = data.result_status === 'REAL FNB TUNNEL — PASS' ? '#4ade80' : '#f87171';
    }

    await refreshFnbTunnelStatus();
  } catch (e) {
    if (banner) banner.textContent = `VALIDATION ERROR: ${e.message}`;
  }
}

async function openFnbWebpageTestUI() {
  const liveLogs = document.getElementById('fnb-live-logs');
  const summary = document.getElementById('fnb-formatted-summary');

  try {
    const res = await fetch('/api/fnb-tunnel/webpage-test', { method: 'POST' });
    const data = await res.json();

    if (liveLogs && data.logs) {
      data.logs.forEach(l => {
        liveLogs.innerHTML += `<div class="log-row log-info">[WEBPAGE] ${escapeHtml(l)}</div>`;
      });
      liveLogs.scrollTop = liveLogs.scrollHeight;
    }

    if (summary) {
      summary.textContent = `Result: ${data.result}\nURL: ${data.url}`;
      summary.style.color = data.result === 'PASS' ? '#4ade80' : '#f87171';
    }
  } catch (e) {
    if (liveLogs) liveLogs.innerHTML += `<div class="log-row log-error">Open Webpage Test Failed: ${escapeHtml(e.message)}</div>`;
  }
}

async function testPlaywrightTunnelUI() {
  const liveLogs = document.getElementById('fnb-live-logs');
  const summary = document.getElementById('fnb-formatted-summary');

  try {
    const res = await fetch('/api/fnb-tunnel/playwright-test', { method: 'POST' });
    const data = await res.json();

    if (liveLogs && data.logs) {
      data.logs.forEach(l => {
        liveLogs.innerHTML += `<div class="log-row log-info">[PLAYWRIGHT] ${escapeHtml(l)}</div>`;
      });
      liveLogs.scrollTop = liveLogs.scrollHeight;
    }

    if (summary && data.formatted_summary) {
      summary.textContent = data.formatted_summary;
      summary.style.color = data.success ? '#4ade80' : '#f87171';
    }
  } catch (e) {
    if (liveLogs) liveLogs.innerHTML += `<div class="log-row log-error">Playwright Test Error: ${escapeHtml(e.message)}</div>`;
  }
}

async function runFnbLoginWorkflowUI() {
  const banner = document.getElementById('fnb-feedback-banner');
  const liveLogs = document.getElementById('fnb-live-logs');
  const summary = document.getElementById('fnb-formatted-summary');

  if (banner) {
    banner.style.display = 'block';
    banner.textContent = 'RUNNING FNB LOGIN + SYNCMYMENU WORKFLOW';
    banner.style.background = 'rgba(234, 179, 8, 0.15)';
    banner.style.color = '#facc15';
  }

  if (summary) {
    summary.textContent = `============================================\n\nFNB LOGIN + SYNCMYMENU WORKFLOW\n\nSTATUS: RUNNING...\n\n============================================`;
  }

  try {
    const res = await fetch('/api/fnb-tunnel/login-workflow', { method: 'POST' });
    const data = await res.json();

    if (liveLogs && data.logs) {
      liveLogs.innerHTML = data.logs.map(l => `<div class="log-row ${l.includes('ERROR') ? 'log-error' : 'log-info'}">${escapeHtml(l)}</div>`).join('');
      liveLogs.scrollTop = liveLogs.scrollHeight;
    }

    if (summary) {
      summary.textContent = data.formatted_summary || `Result: ${data.result_status}`;
      const isPass = data.stages && data.stages.sync_mymenu_page === 'PASS';
      summary.style.color = isPass ? '#4ade80' : '#f87171';
    }

    if (banner) {
      const isPass = data.stages && data.stages.sync_mymenu_page === 'PASS';
      banner.textContent = `FNB LOGIN WORKFLOW FINISHED - RESULT: ${isPass ? 'PASS' : 'FAIL'}`;
      banner.style.background = isPass ? 'rgba(34, 197, 94, 0.2)' : 'rgba(239, 68, 68, 0.2)';
      banner.style.color = isPass ? '#4ade80' : '#f87171';
    }
  } catch (e) {
    if (banner) banner.textContent = `LOGIN WORKFLOW ERROR: ${e.message}`;
  }
}

async function runFnbFetchWorkflowUI() {
  const banner = document.getElementById('fnb-feedback-banner');
  const liveLogs = document.getElementById('fnb-live-logs');
  const summary = document.getElementById('fnb-formatted-summary');

  if (banner) {
    banner.style.display = 'block';
    banner.textContent = 'RUNNING FNB FETCH MENU WORKFLOW';
    banner.style.background = 'rgba(34, 197, 94, 0.15)';
    banner.style.color = '#4ade80';
  }

  if (summary) {
    summary.textContent = `============================================\n\nPHASE 7 — FNB FETCH MENU\n\nSTATUS: RUNNING...\n\n============================================`;
  }

  try {
    const res = await fetch('/api/fnb-tunnel/fetch-workflow', { method: 'POST' });
    const data = await res.json();

    if (liveLogs && data.logs) {
      liveLogs.innerHTML = data.logs.map(l => `<div class="log-row ${l.includes('ERROR') ? 'log-error' : 'log-info'}">${escapeHtml(l)}</div>`).join('');
      liveLogs.scrollTop = liveLogs.scrollHeight;
    }

    if (summary) {
      summary.textContent = data.formatted_summary || `Result: ${data.result_status}`;
      const isPass = data.stages && data.stages.fetch_menu === 'PASS';
      summary.style.color = isPass ? '#4ade80' : '#f87171';
    }

    if (banner) {
      const isPass = data.stages && data.stages.fetch_menu === 'PASS';
      banner.textContent = `PHASE 7 FNB FETCH MENU FINISHED - RESULT: ${isPass ? 'PASS' : 'FAIL'}`;
      banner.style.background = isPass ? 'rgba(34, 197, 94, 0.2)' : 'rgba(239, 68, 68, 0.2)';
      banner.style.color = isPass ? '#4ade80' : '#f87171';
    }
  } catch (e) {
    if (banner) banner.textContent = `FETCH WORKFLOW ERROR: ${e.message}`;
  }
}

async function stopFnbTunnelUI() {
  try {
    await fetch('/api/fnb-tunnel/stop', { method: 'POST' });
    await refreshFnbTunnelStatus();
  } catch (e) {
    console.error("Stop tunnel failed:", e);
  }
}

async function restartFnbTunnelUI() {
  await stopFnbTunnelUI();
  await runFnbTunnelTestUI();
}


// --- OFFICE SSH & GLOBAL TUNNEL SETTINGS ---
async function loadOfficeSshSettings() {
  try {
    const res = await fetch('/api/settings/ssh');
    if (!res.ok) return;
    const cfg = await res.json();

    if (document.getElementById('setting-ssh-host')) document.getElementById('setting-ssh-host').value = cfg.ssh_host || '111.93.205.187';
    if (document.getElementById('setting-ssh-port')) document.getElementById('setting-ssh-port').value = cfg.ssh_port || 22;
    if (document.getElementById('setting-ssh-user')) document.getElementById('setting-ssh-user').value = cfg.ssh_username || 'sourik';
    if (document.getElementById('setting-ssh-key-path')) document.getElementById('setting-ssh-key-path').value = cfg.ssh_key_path || '';
    if (document.getElementById('setting-ssh-host-key')) document.getElementById('setting-ssh-host-key').value = cfg.ssh_host_key || '';

    const passState = document.getElementById('lbl-ssh-pass-state');
    if (passState) {
      passState.textContent = cfg.password_configured ? '******** (Configured)' : 'Not configured';
      passState.style.color = cfg.password_configured ? '#4ade80' : '#f87171';
    }

    if (cfg.auth_type === 'key') {
      if (document.getElementById('rad-ssh-auth-key')) document.getElementById('rad-ssh-auth-key').checked = true;
    } else {
      if (document.getElementById('rad-ssh-auth-pass')) document.getElementById('rad-ssh-auth-pass').checked = true;
    }
  } catch (e) {
    console.error("Error loading Office SSH settings:", e);
  }
}

async function saveOfficeSshSettings() {
  const host = document.getElementById('setting-ssh-host').value.trim();
  const port = parseInt(document.getElementById('setting-ssh-port').value) || 22;
  const user = document.getElementById('setting-ssh-user').value.trim();
  const pass = document.getElementById('setting-ssh-pass').value;
  const keyPath = document.getElementById('setting-ssh-key-path').value.trim();
  const hostKey = document.getElementById('setting-ssh-host-key').value.trim();
  const authMode = document.querySelector('input[name="ssh_auth_mode"]:checked') ? document.querySelector('input[name="ssh_auth_mode"]:checked').value : 'password';

  const payload = {
    ssh_host: host,
    ssh_port: port,
    ssh_username: user,
    auth_type: authMode,
    ssh_key_path: keyPath,
    ssh_host_key: hostKey
  };
  if (pass) {
    payload.ssh_password = pass;
  }

  try {
    const res = await fetch('/api/settings/ssh', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    if (res.ok) {
      alert("Office SSH configuration saved.");
      document.getElementById('setting-ssh-pass').value = "";
      await loadOfficeSshSettings();
      await loadFnbTunnelValidationData();
    } else {
      alert("Failed to save Office SSH configuration.");
    }
  } catch (e) {
    alert("Error saving SSH settings: " + e.message);
  }
}

async function testOfficeSshConnectionUI() {
  const panel = document.getElementById('ssh-test-panel');
  const liveLogs = document.getElementById('ssh-test-live-logs');
  const summary = document.getElementById('ssh-test-summary');

  if (panel) panel.style.display = 'block';

  if (liveLogs) {
    liveLogs.innerHTML = `
      <div class="log-row log-info">[${new Date().toLocaleTimeString()}] Connecting...</div>
      <div class="log-row log-info">[${new Date().toLocaleTimeString()}] Resolving SSH server...</div>
    `;
  }
  if (summary) summary.textContent = "Connecting to SSH server...";

  try {
    const res = await fetch('/api/settings/ssh/test', { method: 'POST' });
    const data = await res.json();

    if (liveLogs && data.logs) {
      liveLogs.innerHTML = data.logs.map(l => `<div class="log-row ${l.includes('ERROR') ? 'log-error' : 'log-info'}">${escapeHtml(l)}</div>`).join('');
      liveLogs.scrollTop = liveLogs.scrollHeight;
    }

    if (summary) {
      summary.textContent = data.formatted_summary || `Result: ${data.result_message}`;
      summary.style.color = data.success ? '#4ade80' : '#f87171';
    }
  } catch (e) {
    if (summary) {
      summary.textContent = `SSH Test Error: ${e.message}`;
      summary.style.color = '#f87171';
    }
  }
}

async function loadGlobalTunnelSettings() {
  try {
    const res = await fetch('/api/settings/tunnel');
    if (!res.ok) return;
    const cfg = await res.json();

    if (document.getElementById('setting-tunnel-remote-port')) document.getElementById('setting-tunnel-remote-port').value = cfg.tunnel_remote_port || 80;
    if (document.getElementById('setting-fnb-service-port')) document.getElementById('setting-fnb-service-port').value = cfg.fnb_service_port || 80;
    if (document.getElementById('setting-web-url-template')) document.getElementById('setting-web-url-template').value = cfg.web_url_template || 'http://127.0.0.1:{local_port}';

    if (cfg.tunnel_type === 'local') {
      if (document.getElementById('rad-tunnel-type-loc')) document.getElementById('rad-tunnel-type-loc').checked = true;
    } else {
      if (document.getElementById('rad-tunnel-type-rev')) document.getElementById('rad-tunnel-type-rev').checked = true;
    }
  } catch (e) {
    console.error("Error loading global tunnel settings:", e);
  }
}

async function saveGlobalTunnelSettings() {
  const remotePort = parseInt(document.getElementById('setting-tunnel-remote-port').value) || 80;
  const servicePort = parseInt(document.getElementById('setting-fnb-service-port').value) || 80;
  const template = document.getElementById('setting-web-url-template').value.trim();
  const tunnelType = document.querySelector('input[name="global_tunnel_type"]:checked') ? document.querySelector('input[name="global_tunnel_type"]:checked').value : 'reverse';

  const payload = {
    tunnel_remote_port: remotePort,
    fnb_service_port: servicePort,
    web_url_template: template,
    tunnel_type: tunnelType
  };

  try {
    const res = await fetch('/api/settings/tunnel', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    if (res.ok) {
      alert("Global Reverse SSH Tunnel configuration saved.");
      await loadGlobalTunnelSettings();
    } else {
      alert("Failed to save global tunnel settings.");
    }
  } catch (e) {
    alert("Error saving tunnel settings: " + e.message);
  }
}


// --- CENTRAL EVENT BINDING ---
function bindEvents() {
  bindClick('btn-select-all', () => {
    document.querySelectorAll('.chk-site-queue').forEach(c => c.checked = true);
    updateSelectedCount();
  });

  bindClick('btn-clear-all', () => {
    document.querySelectorAll('.chk-site-queue').forEach(c => c.checked = false);
    updateSelectedCount();
  });

  bindEvent('chk-queue-header', 'change', (e) => {
    document.querySelectorAll('.chk-site-queue').forEach(c => c.checked = e.target.checked);
    updateSelectedCount();
  });

  bindClick('btn-start-sync', () => {
    const selectedIds = Array.from(document.querySelectorAll('.chk-site-queue:checked')).map(c => parseInt(c.getAttribute('data-id')));
    if (selectedIds.length === 0) {
      alert("Please select at least one site to process.");
      return;
    }
    const countEl = document.getElementById('confirm-site-count');
    if (countEl) countEl.textContent = selectedIds.length;
    const modal = document.getElementById('modal-confirm-real-run');
    if (modal) modal.classList.add('active');
  });

  bindClick('btn-proceed-real-run', () => {
    const modal = document.getElementById('modal-confirm-real-run');
    if (modal) modal.classList.remove('active');
    startAutomation(false);
  });

  bindClick('btn-close-confirm-modal', () => {
    const modal = document.getElementById('modal-confirm-real-run');
    if (modal) modal.classList.remove('active');
  });

  bindClick('btn-cancel-confirm-run', () => {
    const modal = document.getElementById('modal-confirm-real-run');
    if (modal) modal.classList.remove('active');
  });

  bindClick('btn-dry-run', () => startAutomation(true));
  bindClick('btn-stop-automation', stopAutomation);
  bindClick('btn-resume-run', resumeAutomation);

  bindClick('btn-open-add-site-modal', openAddSiteModal);
  bindClick('btn-close-modal-site', () => document.getElementById('modal-site').classList.remove('active'));
  bindClick('btn-cancel-modal-site', () => document.getElementById('modal-site').classList.remove('active'));
  bindClick('btn-save-modal-site', saveSiteModal);

  bindClick('btn-close-modal-history', () => document.getElementById('modal-history-detail').classList.remove('active'));

  bindClick('btn-save-settings', saveSettings);
  bindClick('btn-scan-windows', scanWindows);
  bindClick('btn-detect-putty', detectPuTTYExecutable);
  bindClick('btn-test-plink', testPlinkClick);
  bindClick('btn-test-modal-tunnel', testModalTunnel);

  bindClick('btn-save-office-ssh', saveOfficeSshSettings);
  bindClick('btn-test-office-ssh', testOfficeSshConnectionUI);
  bindClick('btn-save-global-tunnel', saveGlobalTunnelSettings);

  bindClick('btn-toggle-ssh-pass', () => {
    const inp = document.getElementById('setting-ssh-pass');
    if (inp) inp.type = inp.type === 'password' ? 'text' : 'password';
  });

  bindClick('btn-toggle-password', () => {
    const inp = document.getElementById('modal-site-password');
    if (inp) inp.type = inp.type === 'password' ? 'text' : 'password';
  });

  bindEvent('setting-use-custom-plink', 'change', (e) => {
    const grp = document.getElementById('group-custom-plink');
    if (grp) grp.style.display = e.target.checked ? 'block' : 'none';
  });
}


// --- MAIN APPLICATION ENTRY POINT ---
document.addEventListener('DOMContentLoaded', () => {
  console.log("UI INITIALIZED - IRD Sync Automation v1.0");

  // 1. Initialize Sidebar Navigation FIRST (Independent of API calls)
  safeInit("Navigation", initNavigation);

  // 2. Initialize Integration Test Console Explicitly
  safeInit("Integration Test Console", initIntegrationTest);

  // 3. Register Central Button Click Handlers safely
  safeInit("Button Events", bindEvents);

  // 4. Mark UI Health status
  const uiBadge = document.getElementById('badge-ui-health');
  if (uiBadge) {
    uiBadge.textContent = 'UI: READY';
    uiBadge.className = 'status-badge badge-no-action';
  }

  // 5. Execute Backend/API Data Loads Asynchronously (Failures logged, won't break UI)
  safeInit("WebSocket Connection", initWebSocket);
  safeInit("Load Sites", loadSites);
  safeInit("Load Settings", loadSettings);
  safeInit("Load Run History", loadHistory);
  safeInit("Load FNB Tunnel Config", loadFnbTunnelValidationData);
  safeInit("Load Office SSH Config", loadOfficeSshSettings);
  safeInit("Load Global Tunnel Config", loadGlobalTunnelSettings);
});


function escapeHtml(str) {
  if (!str) return '';
  return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
