// IRD Sync Automation Frontend Application Controller
// Version query cache-busting: app.js?v=phase16
console.log("[UI BOOT] PHASE16 app.js EXECUTED");
window.__IRD_PHASE16_JS_LOADED__ = true;
window.__IRD_UI_BUILD__ = "PHASE16-2026-08-28";

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
    if (typeof fn === 'function') {
      fn();
      console.log(`[UI INIT] ${name}: PASS`);
    } else {
      console.warn(`[UI INIT SKIPPED] ${name}: function not defined`);
    }
  } catch (e) {
    console.error(`[UI INIT ERROR] ${name}:`, e);
  }
}

function getApiBaseUrl() {
  if (window.location.origin && window.location.origin !== "null" && window.location.origin !== "file://") {
    return window.location.origin;
  }
  return `http://${window.location.hostname || '127.0.0.1'}:${window.location.port || '18000'}`;
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


// --- DUAL-MODULE NAVIGATION SYSTEM (IRD Automation & DTH Automation) ---
let currentAppModule = 'ird';

function switchAppModule(moduleName, targetTab = null) {
  currentAppModule = moduleName;
  try { localStorage.setItem('active_module', moduleName); } catch(e) {}

  const btnIrd = document.getElementById('btn-module-ird');
  const btnDth = document.getElementById('btn-module-dth');
  const menuIrd = document.getElementById('menu-ird');
  const menuDth = document.getElementById('menu-dth');

  if (moduleName === 'dth') {
    if (btnIrd) { btnIrd.classList.remove('active'); btnIrd.setAttribute('aria-selected', 'false'); }
    if (btnDth) { btnDth.classList.add('active'); btnDth.setAttribute('aria-selected', 'true'); }
    if (menuIrd) menuIrd.classList.remove('active');
    if (menuDth) menuDth.classList.add('active');

    const nextTab = targetTab || localStorage.getItem('active_dth_tab') || 'dth-dashboard';
    navigateToTab(nextTab);
  } else {
    if (btnDth) { btnDth.classList.remove('active'); btnDth.setAttribute('aria-selected', 'false'); }
    if (btnIrd) { btnIrd.classList.add('active'); btnIrd.setAttribute('aria-selected', 'true'); }
    if (menuDth) menuDth.classList.remove('active');
    if (menuIrd) menuIrd.classList.add('active');

    const nextTab = targetTab || localStorage.getItem('active_ird_tab') || 'dashboard';
    navigateToTab(nextTab);
  }
}

function navigateToTab(tabId) {
  // Alias backward-compatible tab IDs
  if (tabId === 'dth') tabId = 'dth-channels';

  const isDthTab = tabId.startsWith('dth-');

  // Sync module switcher buttons & menus
  const btnIrd = document.getElementById('btn-module-ird');
  const btnDth = document.getElementById('btn-module-dth');
  const menuIrd = document.getElementById('menu-ird');
  const menuDth = document.getElementById('menu-dth');

  if (isDthTab) {
    currentAppModule = 'dth';
    try {
      localStorage.setItem('active_module', 'dth');
      localStorage.setItem('active_dth_tab', tabId);
      window.location.hash = `#dth/${tabId.replace('dth-', '')}`;
    } catch(e) {}

    if (btnIrd) { btnIrd.classList.remove('active'); btnIrd.setAttribute('aria-selected', 'false'); }
    if (btnDth) { btnDth.classList.add('active'); btnDth.setAttribute('aria-selected', 'true'); }
    if (menuIrd) menuIrd.classList.remove('active');
    if (menuDth) menuDth.classList.add('active');
  } else {
    currentAppModule = 'ird';
    try {
      localStorage.setItem('active_module', 'ird');
      localStorage.setItem('active_ird_tab', tabId);
      window.location.hash = `#ird/${tabId}`;
    } catch(e) {}

    if (btnDth) { btnDth.classList.remove('active'); btnDth.setAttribute('aria-selected', 'false'); }
    if (btnIrd) { btnIrd.classList.add('active'); btnIrd.setAttribute('aria-selected', 'true'); }
    if (menuDth) menuDth.classList.remove('active');
    if (menuIrd) menuIrd.classList.add('active');
  }

  document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('.tab-page').forEach(p => p.classList.remove('active'));

  const targetNav = document.querySelector(`.nav-btn[data-tab="${tabId}"]`);
  if (targetNav) targetNav.classList.add('active');

  const targetTab = document.getElementById(`tab-${tabId}`);
  if (targetTab) {
    targetTab.classList.add('active');
    console.log(`[NAVIGATION] Switched to tab: ${tabId} (Module: ${currentAppModule})`);
  } else {
    console.warn(`[NAVIGATION WARNING] Tab element #tab-${tabId} not found.`);
  }

  // Trigger lazy component loads on tab switch
  if (tabId === 'sites') safeInit('loadSitesConfigTable', loadSitesConfigTable);
  if (tabId === 'history') safeInit('loadHistory', loadHistory);
  if (tabId === 'settings') safeInit('loadSettingsTabs', () => { loadPuTTYInfo(); loadOfficeSshSettings(); loadGlobalTunnelSettings(); });
  if (tabId === 'diagnostics') safeInit('loadDiagnostics', () => { scanWindows(); loadPackageHealth(); });

  // DTH Pages lazy component loaders
  if (tabId === 'dth-dashboard') safeInit('loadDthDashboard', loadDthDashboard);
  if (tabId === 'dth-sites') safeInit('loadDthSitesConfig', loadDthSitesConfig);
  if (tabId === 'dth-channels') safeInit('initDthTab', initDthTab);
  if (tabId === 'dth-history') safeInit('loadDthHistory', loadDthHistory);
  if (tabId === 'dth-reports') safeInit('loadDthReports', loadDthReports);
  if (tabId === 'dth-settings') safeInit('loadDthSettings', loadDthSettings);
}

function handleHashRouting() {
  const hash = window.location.hash.replace('#', '').trim();
  if (!hash) return;

  if (hash.startsWith('dth/')) {
    const sub = hash.replace('dth/', '');
    const tabId = `dth-${sub}`;
    switchAppModule('dth', tabId);
  } else if (hash.startsWith('ird/')) {
    const tabId = hash.replace('ird/', '');
    switchAppModule('ird', tabId);
  } else if (hash === 'dth') {
    switchAppModule('dth', 'dth-dashboard');
  } else {
    // Legacy direct tab hash
    const el = document.getElementById(`tab-${hash}`);
    if (el) {
      if (hash.startsWith('dth-')) {
        switchAppModule('dth', hash);
      } else {
        switchAppModule('ird', hash);
      }
    }
  }
}

function initNavigation() {
  const btnModuleIrd = document.getElementById('btn-module-ird');
  const btnModuleDth = document.getElementById('btn-module-dth');
  if (btnModuleIrd) {
    btnModuleIrd.addEventListener('click', (e) => {
      e.preventDefault();
      switchAppModule('ird');
    });
  }
  if (btnModuleDth) {
    btnModuleDth.addEventListener('click', (e) => {
      e.preventDefault();
      switchAppModule('dth');
    });
  }

  document.querySelectorAll('.nav-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.preventDefault();
      const tabId = btn.getAttribute('data-tab');
      if (tabId) navigateToTab(tabId);
    });
  });

  // Handle URL hash changes for deep linking & history
  window.addEventListener('hashchange', () => {
    handleHashRouting();
  });

  // Initial routing
  if (window.location.hash) {
    handleHashRouting();
  } else {
    const savedModule = localStorage.getItem('active_module');
    if (savedModule === 'dth') {
      switchAppModule('dth');
    }
  }
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
        } else if (msg.type === 'dth_status') {
          updateDthStatusUI(msg.data);
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


let isStartSyncLocked = false;
let startSyncClickCount = 0;

function handleStartSyncClick() {
  startSyncClickCount++;
  console.log(`[UI] START SYNC click event count: ${startSyncClickCount}`);
  if (isStartSyncLocked) {
    console.warn(`[UI] START SYNC click ignored — handler already locked.`);
    return;
  }
  isStartSyncLocked = true;
  console.log(`[UI] START SYNC request trace ID: STARTSYNC-${Date.now()}`);
  console.log(`[UI] START SYNC request sent`);
  console.log(`[UI] START SYNC handler locked`);
  const btn = document.getElementById("btn-start-sync");
  if (btn) btn.disabled = true;

  console.log("[UI] Confirmation modal opened");
  const modal = document.getElementById('modal-confirm-real-run');
  if (modal) modal.classList.add('active');
}

// --- AUTOMATION STATUS UI UPDATER ---
function updateAutomationStatusUI(statusData) {
  currentRunStatus = statusData;

  const isRunning = statusData.is_running;
  if (!isRunning) {
    isStartSyncLocked = false;
    startSyncClickCount = 0;
  }

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
  console.log("[PHASE17][UI] startAutomation entered (dryRun: " + isDryRun + ")");
  const traceId = "STARTSYNC-" + Date.now();

  const btnStart = document.getElementById("btn-start-sync");
  console.log("[UI] START SYNC button element found:", !!btnStart);
  if (btnStart) {
    console.log(`[UI] START SYNC disabled: ${btnStart.disabled}`);
  }

  let selectedIds = Array.from(document.querySelectorAll('.chk-site-queue:checked')).map(c => parseInt(c.getAttribute('data-id')));
  
  // Fallback 1: If no checkboxes checked in UI table, select all enabled sites from sitesList
  if ((!selectedIds || selectedIds.length === 0) && Array.isArray(sitesList) && sitesList.length > 0) {
    selectedIds = sitesList.filter(s => s.enabled).map(s => s.id);
    console.log(`[UI] Auto-selected ${selectedIds.length} enabled sites for batch run:`, selectedIds);
  }

  // Fallback 2: If sitesList not populated yet, set to null (backend defaults to all enabled sites)
  if (!selectedIds || selectedIds.length === 0) {
    console.log("[UI] No specific site IDs checked, requesting backend run all enabled sites.");
    selectedIds = null;
  }

  console.log(`[PHASE17][UI] Final selected site IDs for payload: ${JSON.stringify(selectedIds)}`);
  console.log("[UI] Selected site IDs:", selectedIds);

  console.log("[UI] startAutomation(false) called");
  console.log(`[PHASE17][UI] window.location.href = ${window.location.href}`);
  console.log(`[PHASE17][UI] window.location.origin = ${window.location.origin}`);

  const baseUrl = getApiBaseUrl();
  console.log(`[PHASE17][UI] API base URL = ${baseUrl}`);

  // Health check call
  console.log(`[PHASE17][UI] Backend health check`);
  try {
    const hRes = await fetch(`${baseUrl}/api/automation/health`).catch(err => ({ ok: false, err }));
    if (hRes.ok) {
      const hData = await hRes.json().catch(() => ({}));
      console.log(`[PHASE17][UI] Backend health: PASS`, hData);
    } else {
      console.warn(`[PHASE17][UI] Backend health check failed:`, hRes);
    }
  } catch (he) {
    console.warn(`[PHASE17][UI] Backend health exception:`, he);
  }

  const endpointPath = isDryRun ? '/api/automation/start-dry-run' : '/api/automation/start-sync';
  const fullUrl = `${baseUrl}${endpointPath}`;
  console.log(`[PHASE17][UI] START SYNC endpoint = ${endpointPath}`);
  console.log(`[PHASE17][UI] Calling backend`);
  console.log(`[PHASE17][UI] API URL: ${fullUrl}`);
  console.log("[UI] API URL:", fullUrl);

  const reqPayload = { site_ids: selectedIds, dry_run: isDryRun, trace_id: traceId };
  console.log(`[PHASE17][UI] Request payload:`, reqPayload);

  // Immediately update status UI to RUNNING
  updateAutomationStatusUI({
    is_running: true,
    operation: isDryRun ? "Starting Dry Run..." : "Starting Sync Automation...",
    progress_percentage: 0,
    status: "STARTING"
  });

  try {
    const res = await fetch(fullUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(reqPayload)
    });

    console.log(`[UI] START SYNC API response received`);
    console.log(`[UI] START SYNC HTTP status: ${res.status}`);
    const data = await res.json().catch(() => ({}));
    console.log(`[UI] START SYNC response body:`, data);

    if (!res.ok) {
      console.error(`[PHASE17][UI] FETCH FAILED - Status: ${res.status}`, data);
      alert(`FAILED — ${data.detail || res.statusText || 'Server Error'}`);
      updateAutomationStatusUI({ is_running: false, operation: "Idle", progress_percentage: 0, status: "READY" });
    } else {
      console.log(`[PHASE17][UI] START SYNC backend request SUCCESS [Trace: ${traceId}]`);
    }
  } catch (e) {
    console.error("[PHASE17][UI] FETCH FAILED", e);
    console.error(`[PHASE17][UI] Error name: ${e.name}`);
    console.error(`[PHASE17][UI] Error message: ${e.message}`);
    alert(`FAILED — Network error: ${e.message}`);
    updateAutomationStatusUI({ is_running: false, operation: "Idle", progress_percentage: 0, status: "READY" });
  }
}

async function stopAutomation() {
  console.log("[UI] STOP AUTOMATION clicked");
  try {
    const btnStop = document.getElementById('btn-stop-automation');
    if (btnStop) btnStop.disabled = true;

    const res = await fetch('/api/automation/stop', { method: 'POST' });
    const data = await res.json();
    console.log("[UI] STOP AUTOMATION API response:", data);

    updateAutomationStatusUI({
      is_running: false,
      operation: "Stopped",
      details: "Automation stopped by user.",
      progress_percentage: 0,
      status: "STOPPED"
    });
  } catch (e) {
    console.error("[UI] Error stopping automation:", e);
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
    const res = await fetch('/api/history');
    if (!res.ok) return;
    const runs = await res.json();
    tbody.innerHTML = '';

    if (!runs || runs.length === 0) {
      tbody.innerHTML = '<tr><td colspan="10" style="text-align: center; color: #94a3b8; padding: 24px;">No automation runs recorded yet today. Click START SYNC to execute.</td></tr>';
      return;
    }

    runs.forEach(r => {
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td>${r.run_date}</td>
        <td>${r.start_time || 'N/A'}</td>
        <td>${r.end_time || 'Running...'}</td>
        <td>${r.total_sites || 0}</td>
        <td>${r.completed_sites || 0}</td>
        <td><strong style="color: var(--accent-amber);">${r.action_points_count || 0}</strong></td>
        <td>${r.no_action_points_count || 0}</td>
        <td><strong style="color: var(--accent-rose, #f87171);">${r.failed_sites_count || 0}</strong></td>
        <td><span class="status-badge ${r.status === 'COMPLETED' ? 'badge-no-action' : (r.status === 'FAILED' ? 'badge-failed' : 'badge-active')}">${r.status}</span></td>
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
    const res = await fetch(`/api/history/${runId}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    const run = data.run || {};
    const results = data.results || [];

    let html = `
      <div style="margin-bottom: 16px; padding: 12px; background: rgba(255,255,255,0.03); border-radius: 8px; font-size: 0.9rem;">
        <div><strong>Run #${run.id}</strong> — Date: <strong>${run.run_date}</strong></div>
        <div style="margin-top: 4px; color: #94a3b8;">
          Start: ${run.start_time || 'N/A'} | End: ${run.end_time || 'Running...'} | Total Sites: ${run.total_sites} | Successful: ${run.completed_sites} | Failed: ${run.failed_sites_count} | Action Points: ${run.action_points_count} | No Action: ${run.no_action_points_count} | Status: <span class="status-badge ${run.status === 'COMPLETED' ? 'badge-ready' : 'badge-failed'}">${run.status}</span>
        </div>
      </div>
      <div class="table-container">
        <table class="data-table">
          <thead>
            <tr>
              <th>Site Name</th>
              <th>Fetch Menu</th>
              <th>Process Latest Menu</th>
              <th>Download</th>
              <th>Action Point Status</th>
              <th>Overall</th>
            </tr>
          </thead>
          <tbody>
    `;

    results.forEach(r => {
      const overallOk = r.status === 'COMPLETED' || r.status === 'SUCCESS' || r.status === 'GOOD';
      const fetchSt = r.fetch_menu_status !== 'UNKNOWN' ? r.fetch_menu_status : (overallOk ? 'SUCCESS' : 'FAILED');
      const procSt = r.process_latest_menu_status !== 'UNKNOWN' ? r.process_latest_menu_status : (overallOk ? 'SUCCESS' : (fetchSt === 'FAILED' ? 'BLOCKED' : 'FAILED'));
      const dlSt = r.download_status !== 'UNKNOWN' ? r.download_status : (overallOk ? 'SUCCESS' : 'BLOCKED');
      const apSt = overallOk ? (r.action_point_status || 'NO ACTION POINT') : '—';

      html += `
        <tr>
          <td><strong>${escapeHtml(r.site_name)}</strong></td>
          <td><span class="status-badge ${fetchSt === 'SUCCESS' || fetchSt === 'PASS' ? 'badge-ready' : 'badge-failed'}">${fetchSt}</span></td>
          <td><span class="status-badge ${procSt === 'SUCCESS' || procSt === 'SKIPPED' || procSt === 'PASS' ? 'badge-ready' : (procSt === 'BLOCKED' ? 'badge-draft' : 'badge-failed')}">${procSt}</span></td>
          <td><span class="status-badge ${dlSt === 'SUCCESS' || dlSt === 'PASS' ? 'badge-ready' : (dlSt === 'BLOCKED' ? 'badge-draft' : 'badge-failed')}">${dlSt}</span></td>
          <td><strong style="color: ${apSt === 'ACTION POINT FOUND' ? 'var(--accent-amber)' : (apSt === 'NO ACTION POINT' ? '#34d399' : '#94a3b8')};">${escapeHtml(apSt)}</strong></td>
          <td><span class="status-badge ${overallOk ? 'badge-ready' : 'badge-failed'}">${overallOk ? 'SUCCESS' : 'FAILED'}</span></td>
        </tr>
      `;
    });

    html += '</tbody></table></div>';
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

// --- DIAGNOSTICS & PACKAGE HEALTH TAB HELPERS ---
async function loadPackageHealth() {
  const badge = document.getElementById('badge-package-overall');
  const container = document.getElementById('package-health-checklist');
  if (badge) {
    badge.textContent = 'CHECKING...';
    badge.className = 'status-badge badge-ready';
  }

  try {
    const res = await fetch('/api/diagnostics/package-health');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    if (badge) {
      badge.textContent = data.overall_status || (data.all_ok ? 'READY' : 'INCOMPLETE');
      badge.className = `status-badge ${data.all_ok ? 'badge-no-action' : 'badge-failed'}`;
    }

    if (container && Array.isArray(data.checks)) {
      container.innerHTML = data.checks.map(c => {
        const badgeClass = c.status === 'PASS' ? 'badge-no-action' : (c.status === 'WARN' || c.status === 'INFO' ? 'badge-action-found' : 'badge-failed');
        return `
          <div style="background: rgba(15, 23, 42, 0.6); border: 1px solid rgba(255,255,255,0.08); border-radius: 8px; padding: 12px 16px;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
              <span style="font-weight: 600; color: #f8fafc; font-size: 0.95rem;">${escapeHtml(c.name)}</span>
              <span class="status-badge ${badgeClass}">${escapeHtml(c.status)}</span>
            </div>
            <div style="font-family: monospace; font-size: 0.8rem; color: #94a3b8; margin-bottom: 4px; word-break: break-all;">${escapeHtml(c.path)}</div>
            <div style="font-size: 0.825rem; color: #cbd5e1;">${escapeHtml(c.description)}</div>
          </div>
        `;
      }).join('');
    }
  } catch (e) {
    console.error("Error loading package health:", e);
    if (badge) {
      badge.textContent = 'ERROR';
      badge.className = 'status-badge badge-failed';
    }
    if (container) {
      container.innerHTML = `<div style="color: var(--accent-red); padding: 12px;">Failed to load package health: ${escapeHtml(e.message)}</div>`;
    }
  }
}

async function scanWindows() {
  const tbody = document.getElementById('tbody-diagnostics');
  if (!tbody) return;

  tbody.innerHTML = `<tr><td colspan="4" style="text-align: center; color: #94a3b8; padding: 20px;">Scanning active desktop windows...</td></tr>`;

  try {
    const res = await fetch('/api/diagnostics/windows');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const windows = await res.json();

    if (!Array.isArray(windows) || windows.length === 0) {
      tbody.innerHTML = `<tr><td colspan="4" style="text-align: center; color: #94a3b8; padding: 20px;">No top-level windows detected</td></tr>`;
      return;
    }

    tbody.innerHTML = windows.map(w => {
      const hwndStr = w.hwnd ? `0x${w.hwnd.toString(16).toUpperCase()}` : 'N/A';
      const procStr = w.process_name ? `${escapeHtml(w.process_name)} (PID: ${w.pid || 'N/A'})` : (w.process || 'N/A');
      const btnList = (w.buttons && w.buttons.length > 0)
        ? w.buttons.map(b => `<span style="display: inline-block; background: rgba(59, 130, 246, 0.15); border: 1px solid rgba(59, 130, 246, 0.3); color: #93c5fd; padding: 2px 6px; border-radius: 4px; font-size: 0.75rem; margin: 2px;">${escapeHtml(b.text || b.class || 'Button')}</span>`).join(' ')
        : `<span style="color: #64748b; font-size: 0.8rem; font-style: italic;">No button controls found</span>`;

      return `
        <tr>
          <td style="font-family: monospace; color: #94a3b8;">${hwndStr}</td>
          <td style="font-weight: 500; color: #e2e8f0;">${procStr}</td>
          <td style="color: #f8fafc; font-weight: 500;">${escapeHtml(w.title || 'Untitled')}</td>
          <td>${btnList}</td>
        </tr>
      `;
    }).join('');
  } catch (e) {
    console.error("Error scanning windows:", e);
    tbody.innerHTML = `<tr><td colspan="4" style="text-align: center; color: var(--accent-red); padding: 20px;">Failed to scan windows: ${escapeHtml(e.message)}</td></tr>`;
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
    const selectedSiteId = document.getElementById('select-test-site') ? parseInt(document.getElementById('select-test-site').value) || 22 : 22;
    const res = await fetch('/api/fnb-tunnel/login-workflow', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ site_id: selectedSiteId })
    });
    const data = await res.json();

    if (liveLogs && data.logs) {
      liveLogs.innerHTML = data.logs.map(l => `<div class="log-row ${l.includes('ERROR') ? 'log-error' : (l.includes('PASS') || l.includes('✓') ? 'log-success' : 'log-info')}">${escapeHtml(l)}</div>`).join('');
      liveLogs.scrollTop = liveLogs.scrollHeight;
    }

    const isSuccess = data.final_status === 'SUCCESS' || data.success === true;

    if (summary) {
      summary.textContent = data.formatted_summary || `Final Result: ${data.final_status || 'FAILED'}\nFailure Code: ${data.failure_code || 'NONE'}`;
      summary.style.color = isSuccess ? '#4ade80' : '#f87171';
    }

    if (banner) {
      banner.textContent = `FNB LOGIN WORKFLOW FINISHED - RESULT: ${isSuccess ? 'PASS' : 'FAIL'}${data.failure_code ? ' (' + data.failure_code + ')' : ''}`;
      banner.style.background = isSuccess ? 'rgba(34, 197, 94, 0.2)' : 'rgba(239, 68, 68, 0.2)';
      banner.style.color = isSuccess ? '#4ade80' : '#f87171';
    }

    await refreshFnbTunnelStatus();
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

  bindClick('btn-start-sync', handleStartSyncClick);

  bindClick('btn-proceed-real-run', () => {
    const pBtn = document.getElementById('btn-proceed-real-run');
    console.log(`[PHASE17][UI] Confirmation button DOM found: ${!!pBtn}`);
    if (pBtn) {
      console.log(`[PHASE17][UI] Confirmation button disabled: ${pBtn.disabled}`);
    }
    console.log(`[PHASE17][UI] Confirmation button click detected`);
    console.log("[UI] REAL RUN confirmation clicked");
    console.log("[UI] CONFIRM REAL RUN clicked");
    const modal = document.getElementById('modal-confirm-real-run');
    if (modal) modal.classList.remove('active');
    console.log("[PHASE17][UI] startAutomation(false) entered");
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


// Delegated Event Handling Safety Mechanism for START SYNC
document.addEventListener("click", function(event) {
  const button = event.target.closest("#btn-start-sync");
  if (!button) {
    return;
  }
  console.log("[UI] START SYNC BUTTON CLICK EVENT FIRED");
  console.log("[UI PHASE16] DELEGATED CLICK FIRED");

  const diagnostic = document.getElementById("phase16-click-status");
  if (diagnostic) {
    diagnostic.textContent = "START SYNC CLICK: FIRED";
    diagnostic.style.background = "rgba(34, 197, 94, 0.4)";
    diagnostic.style.color = "#ffffff";
  }

  startAutomation(false);
});

window.startAutomation = startAutomation;
window.loadPackageHealth = loadPackageHealth;
window.scanWindows = scanWindows;

// --- MAIN APPLICATION ENTRY POINT ---
document.addEventListener('DOMContentLoaded', () => {
  console.log("[UI BOOT] DOMContentLoaded fired");
  console.log("[UI BOOT] PHASE16 JS loaded:", window.__IRD_PHASE16_JS_LOADED__);
  console.log("[UI] app.js loaded");

  const jsStatusEl = document.getElementById("phase16-js-status");
  if (jsStatusEl) {
    jsStatusEl.textContent = "PHASE16 JS: LOADED";
  }

  const startBtn = document.getElementById("btn-start-sync");
  console.log("[UI PHASE16] START SYNC DOM lookup");
  console.log("[UI PHASE16] Button found:", !!startBtn);
  if (startBtn) {
    console.log("[UI PHASE16] Button disabled:", startBtn.disabled);
    console.log("[UI PHASE16] Button tag:", startBtn.tagName);
    console.log("[UI PHASE16] Button text:", startBtn.textContent.trim());

    const rect = startBtn.getBoundingClientRect();
    const style = window.getComputedStyle(startBtn);
    console.log("[UI PHASE16] START SYNC bounding rect:", JSON.stringify(rect));
    console.log("[UI PHASE16] START SYNC pointer-events:", style.pointerEvents);
    console.log("[UI PHASE16] START SYNC z-index:", style.zIndex);
    console.log("[UI PHASE16] START SYNC computed display:", style.display);
    console.log("[UI PHASE16] START SYNC computed visibility:", style.visibility);
    console.log("[UI PHASE16] START SYNC computed opacity:", style.opacity);

    const centerX = rect.left + rect.width / 2;
    const centerY = rect.top + rect.height / 2;
    const elemAtPoint = document.elementFromPoint(centerX, centerY);
    console.log("[UI PHASE16] elementFromPoint:", elemAtPoint ? (elemAtPoint.id || elemAtPoint.tagName) : "null");
  }

  const domStatusEl = document.getElementById("phase16-dom-status");
  if (domStatusEl) {
    domStatusEl.textContent = startBtn ? "START SYNC DOM: FOUND" : "START SYNC DOM: NOT FOUND";
  }

  const btnCount = document.querySelectorAll("#btn-start-sync").length;
  console.log(`[UI PHASE16] START SYNC button count: ${btnCount}`);

  safeInit("Navigation", initNavigation);
  safeInit("Button Events", () => {
    console.log("[UI] Binding START SYNC handler");
    bindEvents();
    console.log("[UI INIT] START SYNC binding: PASS");
  });

  const uiBadge = document.getElementById('badge-ui-health');
  if (uiBadge) {
    uiBadge.textContent = 'UI: READY';
    uiBadge.className = 'status-badge badge-no-action';
  }

  safeInit("WebSocket Connection", initWebSocket);
  safeInit("Load Sites", loadSites);
  safeInit("Load Run History", loadHistory);
  safeInit("Init DTH Module", initDthModule);
});


function escapeHtml(str) {
  if (!str) return '';
  return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

// ==========================================
// DTH CHANNEL CONFIGURATION AUTOMATION UI
// ==========================================

const dthState = {
  uploadedFilename: null,
  uploadedFilePath: null,
  lastRunId: null,
  validationData: null,
  isExecuting: false
};

function initDthTab() {
  console.log("[DTH UI] Initializing DTH Channels Tab...");
  populateDthSitesDropdown();
  bindDthEvents();
  loadDthHistory();
  pollDthStatus();
}

async function populateDthSitesDropdown() {
  const sel = document.getElementById('dth-select-site');
  if (!sel) return;

  try {
    const res = await fetch('/api/dth/sites');
    if (res.ok) {
      const dthSites = await res.json();
      if (dthSites && dthSites.length > 0) {
        sel.innerHTML = '';
        dthSites.forEach(s => {
          const opt = document.createElement('option');
          opt.value = s.id;
          opt.textContent = `${s.name} (Port: ${s.local_port || 18001})`;
          if (s.enabled) opt.selected = true;
          sel.appendChild(opt);
        });
        return;
      }
    }

    const irdRes = await fetch('/api/sites');
    if (irdRes.ok) {
      const sites = await irdRes.json();
      sel.innerHTML = '';
      sites.forEach(site => {
        const opt = document.createElement('option');
        opt.value = site.id;
        opt.textContent = `${site.name} (Port: ${site.local_port || 18001})`;
        if (site.name === "FNB" || site.enabled) opt.selected = true;
        sel.appendChild(opt);
      });
    }
  } catch (e) {
    console.error("[DTH UI] Error populating sites:", e);
  }
}

function bindDthEvents() {
  // 1. Template Downloads
  const btnCsvTpl = document.getElementById('btn-dth-download-csv-template');
  if (btnCsvTpl) btnCsvTpl.onclick = () => window.open('/api/dth/template?format=csv', '_blank');

  const btnXlsxTpl = document.getElementById('btn-dth-download-xlsx-template');
  if (btnXlsxTpl) btnXlsxTpl.onclick = () => window.open('/api/dth/template?format=xlsx', '_blank');

  // 2. File Input Selection
  const fileInput = document.getElementById('dth-file-input');
  if (fileInput) {
    fileInput.onchange = async () => {
      if (fileInput.files && fileInput.files[0]) {
        await uploadDthFile(fileInput.files[0]);
      }
    };
  }

  // 3. Upload & Validate Buttons
  const btnUploadParse = document.getElementById('btn-dth-upload-parse');
  if (btnUploadParse) {
    btnUploadParse.onclick = async () => {
      if (fileInput && fileInput.files && fileInput.files[0]) {
        await uploadDthFile(fileInput.files[0]);
      } else {
        alert("Please select a .csv or .xlsx file first.");
      }
    };
  }

  const btnValidate = document.getElementById('btn-dth-validate');
  if (btnValidate) btnValidate.onclick = () => runDthValidation();

  // 4. Dry Run Button
  const btnDryRun = document.getElementById('btn-dth-dry-run');
  if (btnDryRun) btnDryRun.onclick = () => executeDthRun('DRY_RUN', false);

  // 5. Live Run Confirmation Modal
  const btnStartLive = document.getElementById('btn-dth-start-live');
  if (btnStartLive) {
    btnStartLive.onclick = () => {
      if (!dthState.uploadedFilename) {
        alert("Please upload and validate a channel configuration file first.");
        return;
      }
      const siteSel = document.getElementById('dth-select-site');
      const siteName = siteSel ? siteSel.options[siteSel.selectedIndex].text : "Selected Site";
      const siteLbl = document.getElementById('dth-confirm-site-name');
      if (siteLbl) siteLbl.textContent = siteName;

      const modal = document.getElementById('modal-confirm-dth-run');
      if (modal) modal.classList.add('active');
    };
  }

  const btnCancelConfirm = document.getElementById('btn-cancel-dth-confirm');
  const btnCloseConfirm = document.getElementById('btn-close-dth-confirm-modal');
  const closeDthModal = () => {
    const modal = document.getElementById('modal-confirm-dth-run');
    if (modal) modal.classList.remove('active');
  };
  if (btnCancelConfirm) btnCancelConfirm.onclick = closeDthModal;
  if (btnCloseConfirm) btnCloseConfirm.onclick = closeDthModal;

  const btnProceedLive = document.getElementById('btn-proceed-dth-live');
  if (btnProceedLive) {
    btnProceedLive.onclick = () => {
      closeDthModal();
      executeDthRun('LIVE', true);
    };
  }

  // 6. Stop Button
  const btnStop = document.getElementById('btn-dth-stop');
  if (btnStop) {
    btnStop.onclick = async () => {
      try {
        const res = await fetch('/api/dth/stop', { method: 'POST' });
        const data = await res.json();
        alert(data.message);
      } catch (e) {
        alert("Error requesting stop: " + e.message);
      }
    };
  }

  // 7. Refresh History
  const btnRefreshHist = document.getElementById('btn-dth-refresh-history');
  if (btnRefreshHist) btnRefreshHist.onclick = () => loadDthHistory();

  // 8. Report Downloads
  const btnRepCsv = document.getElementById('btn-dth-export-report-csv');
  if (btnRepCsv) {
    btnRepCsv.onclick = () => {
      if (dthState.lastRunId) window.open(`/api/dth/reports/${dthState.lastRunId}/csv`, '_blank');
    };
  }
  const btnRepJson = document.getElementById('btn-dth-export-report-json');
  if (btnRepJson) {
    btnRepJson.onclick = () => {
      if (dthState.lastRunId) window.open(`/api/dth/reports/${dthState.lastRunId}/json`, '_blank');
    };
  }
}

async function uploadDthFile(file) {
  const lblFilename = document.getElementById('dth-uploaded-filename');
  const lblStatus = document.getElementById('dth-upload-status');
  if (lblStatus) lblStatus.textContent = "Uploading file...";

  const formData = new FormData();
  formData.append('file', file);

  try {
    const res = await fetch('/api/dth/upload', {
      method: 'POST',
      body: formData
    });
    const data = await res.json();
    if (res.ok && data.success) {
      dthState.uploadedFilename = data.filename;
      dthState.uploadedFilePath = data.file_path;
      if (lblFilename) lblFilename.textContent = `Uploaded: ${data.filename} (${(data.size_bytes/1024).toFixed(1)} KB)`;
      if (lblStatus) lblStatus.textContent = "Upload complete. Click Validate & Preview.";
      // Automatically validate
      await runDthValidation();
    } else {
      if (lblStatus) lblStatus.textContent = `Upload failed: ${data.detail || 'Unknown error'}`;
    }
  } catch (e) {
    if (lblStatus) lblStatus.textContent = `Upload error: ${e.message}`;
  }
}

async function runDthValidation() {
  if (!dthState.uploadedFilename) {
    alert("Please select and upload a configuration file first.");
    return;
  }

  const lblStatus = document.getElementById('dth-upload-status');
  if (lblStatus) lblStatus.textContent = "Validating records...";

  const imgDirInput = document.getElementById('dth-image-dir-input');
  const imgDir = imgDirInput ? imgDirInput.value.trim() : "";

  const formData = new FormData();
  formData.append('filename', dthState.uploadedFilename);
  if (imgDir) formData.append('image_dir', imgDir);

  try {
    const res = await fetch('/api/dth/validate', {
      method: 'POST',
      body: formData
    });
    const data = await res.json();
    if (res.ok && data.success) {
      dthState.validationData = data;
      updateDthKpis(data);
      renderDthPreviewTable(data.items, data.validation_results);
      if (lblStatus) lblStatus.textContent = `Validation finished: ${data.valid_rows} ready, ${data.invalid_rows} invalid, ${data.duplicate_rows} duplicates.`;
    } else {
      const err = data.parse_errors ? data.parse_errors.join('; ') : (data.detail || "Validation failed");
      alert("Validation failed: " + err);
      if (lblStatus) lblStatus.textContent = err;
    }
  } catch (e) {
    console.error("[DTH UI] Validation error:", e);
    if (lblStatus) lblStatus.textContent = "Error: " + e.message;
  }
}

function updateDthKpis(data) {
  const elTotal = document.getElementById('dth-stat-total');
  const elValid = document.getElementById('dth-stat-valid');
  const elInvalid = document.getElementById('dth-stat-invalid');
  const elDuplicates = document.getElementById('dth-stat-duplicates');

  if (elTotal) elTotal.textContent = data.total_rows || 0;
  if (elValid) elValid.textContent = data.valid_rows || 0;
  if (elInvalid) elInvalid.textContent = data.invalid_rows || 0;
  if (elDuplicates) elDuplicates.textContent = data.duplicate_rows || 0;
}

function renderDthPreviewTable(items, results) {
  const tbody = document.getElementById('tbody-dth-channels');
  if (!tbody) return;

  if (!items || items.length === 0) {
    tbody.innerHTML = `<tr><td colspan="9" style="text-align: center; color: var(--text-muted); padding: 30px;">No channels found in file.</td></tr>`;
    return;
  }

  let html = '';
  items.forEach((item, idx) => {
    const vr = results && results[idx] ? results[idx] : null;
    const status = vr ? vr.status : 'PENDING';
    const statusClass = getDthStatusBadgeClass(status);

    const categories = item.categories || [];
    const catBadges = categories.map(c => {
      const isMandatory = c.toLowerCase() === 'all';
      return `<span class="dth-cat-tag ${isMandatory ? 'mandatory' : ''}">${escapeHtml(c)}</span>`;
    }).join(' ');

    const details = vr ? (vr.errors.length ? vr.errors.join('; ') : (vr.warnings.length ? vr.warnings.join('; ') : 'OK')) : '';

    html += `
      <tr>
        <td>${item.row_number}</td>
        <td><strong>${escapeHtml(item.channel_number)}</strong></td>
        <td>${escapeHtml(item.name)}</td>
        <td>${escapeHtml(item.osd)}</td>
        <td>${catBadges}</td>
        <td><small style="color: var(--text-muted);">${escapeHtml(item.image)}</small></td>
        <td><span class="status-badge ${statusClass}">${escapeHtml(status)}</span></td>
        <td>${status === 'SKIPPED_DUPLICATE' ? 'ALREADY IN PORTAL' : '-'}</td>
        <td style="font-size: 12px; color: ${status === 'INVALID' ? 'var(--accent-red)' : 'var(--text-muted)'};">${escapeHtml(details)}</td>
      </tr>
    `;
  });
  tbody.innerHTML = html;
}

function getDthStatusBadgeClass(status) {
  switch (status) {
    case 'READY': return 'badge-dth-ready';
    case 'SUCCESS': return 'badge-dth-success';
    case 'INVALID': return 'badge-dth-invalid';
    case 'SKIPPED_DUPLICATE': return 'badge-dth-duplicate';
    case 'UNKNOWN': return 'badge-dth-unknown';
    case 'FAILED': return 'badge-dth-failed';
    default: return 'badge-dth-ready';
  }
}

async function executeDthRun(mode, authorized) {
  if (!dthState.uploadedFilename) {
    alert("Please upload and validate a channel configuration file first.");
    return;
  }

  const siteSel = document.getElementById('dth-select-site');
  const siteId = siteSel ? parseInt(siteSel.value) : 1;
  const imgDirInput = document.getElementById('dth-image-dir-input');
  const imgDir = imgDirInput ? imgDirInput.value.trim() : "";
  const delayInput = document.getElementById('dth-delay-input');
  const delay = delayInput ? parseFloat(delayInput.value) || 1.0 : 1.0;

  const modeBadge = document.getElementById('badge-dth-mode');
  if (modeBadge) {
    modeBadge.textContent = `MODE: ${mode}`;
    modeBadge.className = `status-badge ${mode === 'LIVE' ? 'badge-dth-failed' : 'badge-dth-ready'}`;
  }

  try {
    const payload = {
      filename: dthState.uploadedFilename,
      image_dir: imgDir,
      mode: mode,
      site_id: siteId,
      channel_delay_seconds: delay,
      authorized: authorized
    };

    const res = await fetch('/api/dth/execute', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (res.ok && data.success) {
      console.log(`[DTH UI] ${mode} execution started successfully.`);
      dthState.isExecuting = true;
      toggleDthActionButtons(true);
      pollDthStatus();
    } else {
      alert(`Could not start ${mode}: ${data.detail || 'Unknown error'}`);
    }
  } catch (e) {
    alert("Execution error: " + e.message);
  }
}

function toggleDthActionButtons(isRunning) {
  const btnStart = document.getElementById('btn-dth-start-live');
  const btnDry = document.getElementById('btn-dth-dry-run');
  const btnValidate = document.getElementById('btn-dth-validate');
  const btnStop = document.getElementById('btn-dth-stop');

  if (btnStart) btnStart.disabled = isRunning;
  if (btnDry) btnDry.disabled = isRunning;
  if (btnValidate) btnValidate.disabled = isRunning;
  if (btnStop) btnStop.disabled = !isRunning;
}

function updateDthStatusUI(statusData) {
  if (!statusData) return;

  const isRunning = !!statusData.is_running;
  toggleDthActionButtons(isRunning);

  const elOp = document.getElementById('dth-status-operation');
  if (elOp) elOp.textContent = `Status: ${statusData.operation || statusData.status || 'Idle'}`;

  const elCh = document.getElementById('dth-status-current-channel');
  if (elCh) elCh.textContent = `Current: ${statusData.current_channel || 'None'}`;

  const elProgress = document.getElementById('dth-progress-bar-fill');
  if (elProgress) elProgress.style.width = `${statusData.progress_percentage || 0}%`;

  const dot = document.getElementById('dth-status-dot');
  if (dot) dot.style.background = isRunning ? 'var(--accent-green)' : 'var(--text-muted)';

  if (statusData.run_id) {
    dthState.lastRunId = statusData.run_id;
    const btnCsv = document.getElementById('btn-dth-export-report-csv');
    const btnJson = document.getElementById('btn-dth-export-report-json');
    if (btnCsv) btnCsv.disabled = false;
    if (btnJson) btnJson.disabled = false;
  }

  // Also update Dashboard Tab banner
  if (typeof updateDthDashboardActiveBanner === 'function') {
    updateDthDashboardActiveBanner(statusData);
  }

  // Refresh history, dashboard, and reports when execution completes
  if (!isRunning && dthState.isExecuting) {
    dthState.isExecuting = false;
    loadDthHistory();
    if (typeof loadDthDashboard === 'function') loadDthDashboard();
    if (typeof loadDthReports === 'function') loadDthReports();
  }
}

let dthPollInterval = null;
function pollDthStatus() {
  if (dthPollInterval) clearInterval(dthPollInterval);
  dthPollInterval = setInterval(async () => {
    try {
      const res = await fetch('/api/dth/status');
      const data = await res.json();
      updateDthStatusUI(data);
      if (!data.is_running && !dthState.isExecuting) {
        clearInterval(dthPollInterval);
        dthPollInterval = null;
      }
    } catch (e) {
      // Ignore background polling errors
    }
  }, 2000);
}

async function loadDthHistory() {
  const tbody = document.getElementById('tbody-dth-history');
  const countBadge = document.getElementById('dth-history-count-badge');
  if (!tbody) return;

  try {
    const res = await fetch('/api/dth/history?limit=50');
    const data = await res.json();
    const runs = data.runs || [];

    if (countBadge) countBadge.textContent = `${runs.length} Run${runs.length === 1 ? '' : 's'}`;

    if (!res.ok || runs.length === 0) {
      tbody.innerHTML = `<tr><td colspan="12" style="text-align: center; color: var(--text-muted); padding: 25px;">No past DTH execution runs recorded.</td></tr>`;
      return;
    }

    let html = '';
    runs.forEach(r => {
      const statusBadge = r.status === 'COMPLETED' ? 'badge-dth-success' : (r.status === 'STOPPED' ? 'badge-dth-duplicate' : 'badge-dth-failed');
      const modeBadge = r.mode === 'LIVE' ? 'badge-dth-failed' : 'badge-dth-ready';

      html += `
        <tr>
          <td><strong>#${r.id}</strong></td>
          <td>${escapeHtml(r.run_date || '')}</td>
          <td><small>${escapeHtml(r.start_time || '')} - ${escapeHtml(r.end_time || 'In Progress')}</small></td>
          <td><span class="status-badge ${modeBadge}">${r.mode}</span></td>
          <td>${escapeHtml(r.site_name || 'FNB')}</td>
          <td><small style="word-break: break-all;">${escapeHtml(r.filename || '')}</small></td>
          <td>${r.total_channels || 0}</td>
          <td style="color: var(--accent-green); font-weight: 600;">${r.successful_channels || 0}</td>
          <td style="color: var(--accent-amber);">${r.skipped_duplicates || 0}</td>
          <td style="color: var(--accent-red);">${(r.failed_channels || 0) + (r.invalid_channels || 0)}</td>
          <td><span class="status-badge ${statusBadge}">${r.status}</span></td>
          <td>
            <div style="display: flex; gap: 4px; align-items: center;">
              <button class="btn btn-secondary btn-sm" onclick="openDthRunDetails(${r.id})">Details</button>
              <a href="/api/dth/reports/${r.id}/csv" target="_blank" class="btn btn-secondary btn-sm" title="Download CSV">CSV</a>
              <a href="/api/dth/reports/${r.id}/json" target="_blank" class="btn btn-secondary btn-sm" title="Download JSON">JSON</a>
            </div>
          </td>
        </tr>
      `;
    });
    tbody.innerHTML = html;
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="12" style="text-align: center; color: var(--accent-red); padding: 20px;">Error loading history: ${escapeHtml(e.message)}</td></tr>`;
  }
}

// ==========================================
// DTH MODULE CONTROLLERS & DATA LOGIC
// ==========================================

// 1. DTH DASHBOARD CONTROLLER
async function loadDthDashboard() {
  console.log("[DTH UI] Loading DTH Dashboard...");
  try {
    const res = await fetch('/api/dth/dashboard');
    if (!res.ok) {
      console.warn("[DTH UI] /api/dth/dashboard returned non-ok, falling back to /api/dth/stats");
      const fallbackRes = await fetch('/api/dth/stats');
      if (fallbackRes.ok) {
        const stats = await fallbackRes.json();
        updateDthDashboardMetrics(stats);
      }
      return;
    }
    const data = await res.json();
    const metrics = data.metrics || {};
    updateDthDashboardMetrics(metrics);

    // Render Recent Runs table on Dashboard
    renderDthDashboardRecentRuns(data.recent_runs || []);

    // Render Sites Overview table on Dashboard
    renderDthDashboardSitesOverview(data.sites || []);

    // Sync active run banner on Dashboard
    if (data.active_run) {
      updateDthDashboardActiveBanner(data.active_run);
    }
  } catch (e) {
    console.error("[DTH UI] Error loading DTH Dashboard:", e);
  }
}

function updateDthDashboardMetrics(m) {
  const elSites = document.getElementById('dth-dash-stat-sites');
  const elProc = document.getElementById('dth-dash-stat-processed');
  const elSucc = document.getElementById('dth-dash-stat-success');
  const elFail = document.getElementById('dth-dash-stat-failed');
  const elDup = document.getElementById('dth-dash-stat-duplicates');
  const elRuns = document.getElementById('dth-dash-stat-runs');

  if (elSites) elSites.textContent = m.configured_sites || 0;
  if (elProc) elProc.textContent = m.channels_processed || 0;
  if (elSucc) elSucc.textContent = m.successful_creations || 0;
  if (elFail) elFail.textContent = m.failed_operations || 0;
  if (elDup) elDup.textContent = m.skipped_duplicates || 0;
  if (elRuns) elRuns.textContent = m.total_runs || 0;
}

function renderDthDashboardRecentRuns(runs) {
  const tbody = document.getElementById('tbody-dth-dash-runs');
  if (!tbody) return;

  if (!runs || runs.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="7" style="text-align: center; color: var(--text-muted); padding: 35px 20px;">
          <div style="font-size: 15px; margin-bottom: 6px;">No DTH runs recorded yet</div>
          <div style="font-size: 12px; margin-bottom: 12px;">Import a channel configuration file to execute your first batch run.</div>
          <button class="btn btn-secondary btn-sm" onclick="navigateToTab('dth-channels')">Go to Channel Configuration</button>
        </td>
      </tr>
    `;
    return;
  }

  let html = '';
  runs.slice(0, 7).forEach(r => {
    const statusBadge = r.status === 'COMPLETED' ? 'badge-dth-success' : (r.status === 'STOPPED' ? 'badge-dth-duplicate' : 'badge-dth-failed');
    const modeBadge = r.mode === 'LIVE' ? 'badge-dth-failed' : 'badge-dth-ready';
    html += `
      <tr style="cursor: pointer;" onclick="openDthRunDetails(${r.id})" title="Click to inspect row-level channel results">
        <td><strong>#${r.id}</strong></td>
        <td>${escapeHtml(r.run_date || '')}</td>
        <td>${escapeHtml(r.site_name || 'FNB')}</td>
        <td><span class="status-badge ${modeBadge}">${r.mode}</span></td>
        <td>${r.total_channels || 0}</td>
        <td style="color: var(--accent-green); font-weight: 600;">${r.successful_channels || 0}</td>
        <td><span class="status-badge ${statusBadge}">${r.status}</span></td>
      </tr>
    `;
  });
  tbody.innerHTML = html;
}

function renderDthDashboardSitesOverview(sites) {
  const tbody = document.getElementById('tbody-dth-dash-sites');
  if (!tbody) return;

  if (!sites || sites.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="4" style="text-align: center; color: var(--text-muted); padding: 35px 20px;">
          <div style="font-size: 15px; margin-bottom: 6px;">No DTH sites configured</div>
          <div style="font-size: 12px; margin-bottom: 12px;">Add a target portal site to enable channel automation.</div>
          <button class="btn btn-primary btn-sm" onclick="navigateToTab('dth-sites')">+ Configure Sites</button>
        </td>
      </tr>
    `;
    return;
  }

  let html = '';
  sites.forEach(s => {
    const stateBadge = s.enabled ? '<span class="status-badge badge-ready">Enabled</span>' : '<span class="status-badge" style="color: var(--text-muted);">Disabled</span>';
    const targetUrl = s.portal_url || `localhost:${s.local_port || 18001}`;
    html += `
      <tr>
        <td><strong>${escapeHtml(s.name)}</strong></td>
        <td><small style="color: var(--accent-cyan); word-break: break-all;">${escapeHtml(targetUrl)}</small></td>
        <td>${stateBadge}</td>
        <td>
          <button class="btn btn-secondary btn-sm" onclick="testDthSiteFromTable(${s.id}, this)">Check</button>
        </td>
      </tr>
    `;
  });
  tbody.innerHTML = html;
}

function updateDthDashboardActiveBanner(statusData) {
  const isRunning = !!statusData.is_running;
  const dot = document.getElementById('dth-dash-status-dot');
  const op = document.getElementById('dth-dash-status-operation');
  const ch = document.getElementById('dth-dash-status-channel');
  const fill = document.getElementById('dth-dash-progress-bar-fill');
  const btnStop = document.getElementById('btn-dth-dash-stop');

  if (dot) dot.style.background = isRunning ? 'var(--accent-green)' : 'var(--text-muted)';
  if (op) op.textContent = `Execution Status: ${statusData.operation || statusData.status || (isRunning ? 'Running' : 'Idle')}`;
  if (ch) ch.textContent = `Current: ${statusData.current_channel || 'None'}`;
  if (fill) fill.style.width = `${statusData.progress_percentage || 0}%`;
  if (btnStop) btnStop.style.display = isRunning ? 'inline-block' : 'none';
}

// 2. DTH SITES CONFIGURATION CONTROLLER
let dthSitesCache = [];

async function loadDthSitesConfig() {
  const tbody = document.getElementById('tbody-dth-sites-table');
  const countBadge = document.getElementById('dth-sites-count-badge');
  if (!tbody) return;

  try {
    const res = await fetch('/api/dth/sites');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const sites = await res.json();
    dthSitesCache = sites;

    if (countBadge) countBadge.textContent = `${sites.length} Site${sites.length === 1 ? '' : 's'}`;

    if (!sites || sites.length === 0) {
      tbody.innerHTML = `
        <tr>
          <td colspan="9" style="text-align: center; color: var(--text-muted); padding: 40px 20px;">
            <div style="font-size: 16px; margin-bottom: 8px;">No DTH sites configured yet</div>
            <div style="font-size: 13px; margin-bottom: 16px;">Create independent DTH portal configurations or import copies from IRD sites.</div>
            <div style="display: flex; justify-content: center; gap: 10px;">
              <button class="btn btn-primary" onclick="openAddDthSiteModal()">+ Add DTH Site</button>
              <button class="btn btn-secondary" onclick="importIrdSitesToDth()">Copy from IRD Sites</button>
            </div>
          </td>
        </tr>
      `;
      return;
    }

    let html = '';
    sites.forEach(s => {
      const stateBadge = s.enabled
        ? `<span class="status-badge badge-ready" style="cursor: pointer;" onclick="toggleDthSite(${s.id})" title="Click to toggle">Enabled</span>`
        : `<span class="status-badge" style="color: var(--text-muted); cursor: pointer;" onclick="toggleDthSite(${s.id})" title="Click to toggle">Disabled</span>`;

      const credBadge = s.has_credentials
        ? `<span class="status-badge badge-ready" title="Protected in encrypted vault">Encrypted</span>`
        : `<span class="status-badge" style="color: var(--text-muted);">None</span>`;

      const tunnelInfo = s.ssh_host
        ? `SSH: ${escapeHtml(s.ssh_host)}:${s.ssh_port || 22}`
        : (s.putty_session ? `PuTTY: ${escapeHtml(s.putty_session)}` : `Port ${s.local_port || 18001}`);

      const portalDisplay = s.portal_url || `http://localhost:${s.local_port || 18001}/zmp/main-menu.do`;

      html += `
        <tr>
          <td>#${s.id}</td>
          <td><strong>${escapeHtml(s.name)}</strong></td>
          <td><small style="color: var(--accent-cyan); word-break: break-all;">${escapeHtml(portalDisplay)}</small></td>
          <td>${escapeHtml(s.idp_username || 'admin')}</td>
          <td>${credBadge}</td>
          <td><small style="color: var(--text-muted);">${escapeHtml(tunnelInfo)}</small></td>
          <td>${stateBadge}</td>
          <td id="dth-site-conn-${s.id}">
            <button class="btn btn-secondary btn-sm" onclick="testDthSiteFromTable(${s.id}, this)">Test</button>
          </td>
          <td>
            <div style="display: flex; gap: 6px;">
              <button class="btn btn-secondary btn-sm" onclick="openEditDthSiteModal(${s.id})">Edit</button>
              <button class="btn btn-danger btn-sm" onclick="deleteDthSite(${s.id}, '${escapeHtml(s.name)}')">Delete</button>
            </div>
          </td>
        </tr>
      `;
    });
    tbody.innerHTML = html;

    // Keep Channel selector up to date
    populateDthSitesDropdown();
  } catch (e) {
    console.error("[DTH UI] Error loading DTH sites:", e);
    tbody.innerHTML = `<tr><td colspan="9" style="text-align: center; color: var(--accent-red); padding: 25px;">Error loading DTH sites: ${escapeHtml(e.message)}</td></tr>`;
  }
}

// 3. DTH SITE MODAL & ACTIONS
function openAddDthSiteModal() {
  const modal = document.getElementById('modal-dth-site');
  if (!modal) return;

  const title = document.getElementById('modal-dth-site-title');
  if (title) title.textContent = "Add New DTH Site Configuration";

  const setVal = (id, val) => { const el = document.getElementById(id); if (el) el.value = val; };
  setVal('modal-dth-site-id', "");
  setVal('modal-dth-site-name', "");
  setVal('modal-dth-portal-url', "");
  setVal('modal-dth-local-port', "18001");
  setVal('modal-dth-site-ip', "");
  setVal('modal-dth-site-port', "80");
  setVal('modal-dth-idp-username', "admin");
  setVal('modal-dth-idp-password', "");
  setVal('modal-dth-ssh-host', "");
  setVal('modal-dth-ssh-port', "22");
  setVal('modal-dth-ssh-username', "");
  setVal('modal-dth-ssh-password', "");
  setVal('modal-dth-putty-session', "");
  setVal('modal-dth-notes', "");

  const chk = document.getElementById('modal-dth-enabled');
  if (chk) chk.checked = true;

  modal.classList.add('active');
}

async function openEditDthSiteModal(siteId) {
  const modal = document.getElementById('modal-dth-site');
  if (!modal) return;

  try {
    const res = await fetch(`/api/dth/sites/${siteId}`);
    const data = await res.json();
    const s = data.site || data;

    const title = document.getElementById('modal-dth-site-title');
    if (title) title.textContent = `Edit DTH Site: ${s.name}`;

    const setVal = (id, val) => { const el = document.getElementById(id); if (el) el.value = val !== null && val !== undefined ? val : ""; };
    setVal('modal-dth-site-id', s.id);
    setVal('modal-dth-site-name', s.name);
    setVal('modal-dth-portal-url', s.portal_url);
    setVal('modal-dth-local-port', s.local_port || 18001);
    setVal('modal-dth-site-ip', s.remote_host);
    setVal('modal-dth-site-port', s.remote_port || 80);
    setVal('modal-dth-idp-username', s.idp_username || "admin");
    setVal('modal-dth-idp-password', ""); // Do not expose password
    setVal('modal-dth-ssh-host', s.ssh_host);
    setVal('modal-dth-ssh-port', s.ssh_port || 22);
    setVal('modal-dth-ssh-username', s.ssh_username);
    setVal('modal-dth-ssh-password', ""); // Do not expose password
    setVal('modal-dth-putty-session', s.putty_session);
    setVal('modal-dth-notes', s.notes);

    const chk = document.getElementById('modal-dth-enabled');
    if (chk) chk.checked = !!s.enabled;

    modal.classList.add('active');
  } catch (e) {
    alert("Error loading DTH site: " + e.message);
  }
}

function closeDthSiteModal() {
  const modal = document.getElementById('modal-dth-site');
  if (modal) modal.classList.remove('active');
}

async function saveDthSite() {
  const nameInput = document.getElementById('modal-dth-site-name');
  const name = nameInput ? nameInput.value.trim() : "";
  if (!name) {
    alert("Please enter a site name.");
    return;
  }

  const idVal = document.getElementById('modal-dth-site-id')?.value;
  const isEdit = !!idVal;
  const siteId = isEdit ? parseInt(idVal) : null;

  const payload = {
    name: name,
    portal_url: document.getElementById('modal-dth-portal-url')?.value.trim() || null,
    local_port: parseInt(document.getElementById('modal-dth-local-port')?.value) || 18001,
    remote_host: document.getElementById('modal-dth-site-ip')?.value.trim() || null,
    remote_port: parseInt(document.getElementById('modal-dth-site-port')?.value) || 80,
    idp_username: document.getElementById('modal-dth-idp-username')?.value.trim() || "admin",
    ssh_host: document.getElementById('modal-dth-ssh-host')?.value.trim() || null,
    ssh_port: parseInt(document.getElementById('modal-dth-ssh-port')?.value) || 22,
    ssh_username: document.getElementById('modal-dth-ssh-username')?.value.trim() || null,
    putty_session: document.getElementById('modal-dth-putty-session')?.value.trim() || null,
    notes: document.getElementById('modal-dth-notes')?.value.trim() || null,
    enabled: document.getElementById('modal-dth-enabled')?.checked ?? true
  };

  const idpPass = document.getElementById('modal-dth-idp-password')?.value;
  if (idpPass) payload.idp_password = idpPass;

  const sshPass = document.getElementById('modal-dth-ssh-password')?.value;
  if (sshPass) payload.ssh_password = sshPass;

  try {
    const url = isEdit ? `/api/dth/sites/${siteId}` : '/api/dth/sites';
    const method = isEdit ? 'PUT' : 'POST';
    const res = await fetch(url, {
      method: method,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (!res.ok) {
      alert(`Error saving DTH site: ${data.detail || 'Failed'}`);
      return;
    }

    closeDthSiteModal();
    loadDthSitesConfig();
    loadDthDashboard();
  } catch (e) {
    alert("Error saving DTH site: " + e.message);
  }
}

async function deleteDthSite(siteId, siteName) {
  if (!confirm(`Are you sure you want to delete DTH site "${siteName}"? This action cannot be undone.`)) {
    return;
  }

  try {
    const res = await fetch(`/api/dth/sites/${siteId}`, { method: 'DELETE' });
    const data = await res.json();
    if (res.status === 409) {
      alert("Cannot delete site: it is currently being used by an active DTH run.");
      return;
    }
    if (!res.ok) {
      alert(`Could not delete site: ${data.detail || 'Error'}`);
      return;
    }
    loadDthSitesConfig();
    loadDthDashboard();
  } catch (e) {
    alert("Error deleting DTH site: " + e.message);
  }
}

async function toggleDthSite(siteId) {
  try {
    const res = await fetch(`/api/dth/sites/${siteId}/toggle`, { method: 'POST' });
    if (res.ok) {
      loadDthSitesConfig();
      loadDthDashboard();
    }
  } catch (e) {
    console.error("[DTH UI] Error toggling site:", e);
  }
}

async function testDthSiteFromTable(siteId, btnEl) {
  if (btnEl) {
    btnEl.disabled = true;
    btnEl.textContent = "...";
  }

  try {
    const res = await fetch(`/api/dth/sites/${siteId}/test`, { method: 'POST' });
    const data = await res.json();
    const cell = document.getElementById(`dth-site-conn-${siteId}`);
    if (cell) {
      if (data.success) {
        cell.innerHTML = `<span class="status-badge badge-dth-success" title="${escapeHtml(data.message)}">OK</span>`;
      } else {
        cell.innerHTML = `<span class="status-badge badge-dth-failed" title="${escapeHtml(data.message || data.detail)}">Failed</span>`;
      }
    } else if (btnEl) {
      btnEl.textContent = data.success ? "OK" : "Failed";
    }
  } catch (e) {
    if (btnEl) btnEl.textContent = "Err";
  } finally {
    if (btnEl) btnEl.disabled = false;
  }
}

async function importIrdSitesToDth() {
  if (!confirm("Import existing IRD sites into DTH site configurations as independent copies?")) {
    return;
  }

  try {
    const res = await fetch('/api/dth/sites/import-ird', { method: 'POST' });
    const data = await res.json();
    if (res.ok) {
      alert(data.message || `Imported ${data.imported_count || 0} sites.`);
      loadDthSitesConfig();
      loadDthDashboard();
    } else {
      alert(`Import failed: ${data.detail || 'Error'}`);
    }
  } catch (e) {
    alert("Error importing IRD sites: " + e.message);
  }
}

// 4. RUN DETAILS MODAL INSPECTOR
async function openDthRunDetails(runId) {
  const modal = document.getElementById('modal-dth-run-details');
  if (!modal) return;

  const title = document.getElementById('modal-dth-run-details-title');
  if (title) title.textContent = `DTH Run #${runId} Details (Loading...)`;

  modal.classList.add('active');

  try {
    const res = await fetch(`/api/dth/runs/${runId}`);
    if (!res.ok) throw new Error("Could not fetch run details");
    const data = await res.json();
    const run = data.run;
    const items = data.items || [];

    if (title) title.textContent = `DTH Run #${run.id} Details (${run.run_date || ''} - ${run.status})`;

    const elSite = document.getElementById('modal-dth-run-site');
    const elMode = document.getElementById('modal-dth-run-mode');
    const elTot = document.getElementById('modal-dth-run-total');
    const elSucc = document.getElementById('modal-dth-run-success');
    const elSkip = document.getElementById('modal-dth-run-skipped');
    const elFail = document.getElementById('modal-dth-run-failed');

    if (elSite) elSite.textContent = run.site_name || 'FNB';
    if (elMode) elMode.textContent = run.mode || 'DRY_RUN';
    if (elTot) elTot.textContent = run.total_channels || 0;
    if (elSucc) elSucc.textContent = run.successful_channels || 0;
    if (elSkip) elSkip.textContent = run.skipped_duplicates || 0;
    if (elFail) elFail.textContent = (run.failed_channels || 0) + (run.invalid_channels || 0);

    const btnCsv = document.getElementById('btn-modal-dth-download-csv');
    const btnJson = document.getElementById('btn-modal-dth-download-json');
    if (btnCsv) btnCsv.href = `/api/dth/reports/${run.id}/csv`;
    if (btnJson) btnJson.href = `/api/dth/reports/${run.id}/json`;

    // Populate row items
    const tbody = document.getElementById('tbody-modal-dth-channels');
    if (tbody) {
      if (items.length === 0) {
        tbody.innerHTML = `<tr><td colspan="9" style="text-align: center; color: var(--text-muted); padding: 25px;">No channel row records found for this run.</td></tr>`;
      } else {
        let html = '';
        items.forEach((item, idx) => {
          const statusClass = getDthStatusBadgeClass(item.status);
          const catBadges = (item.categories || []).map(c => `<span class="dth-cat-tag ${c.toLowerCase() === 'all' ? 'mandatory' : ''}">${escapeHtml(c)}</span>`).join(' ');
          const dur = item.duration_seconds ? `${item.duration_seconds.toFixed(1)}s` : '-';
          const verified = item.verified ? '<span style="color: var(--accent-green);">YES</span>' : '<span style="color: var(--text-muted);">NO</span>';

          html += `
            <tr>
              <td>${item.row_number || (idx + 1)}</td>
              <td><strong>${escapeHtml(item.channel_number || '')}</strong></td>
              <td>${escapeHtml(item.name || '')}</td>
              <td>${escapeHtml(item.osd || '')}</td>
              <td>${catBadges}</td>
              <td><span class="status-badge ${statusClass}">${item.status}</span></td>
              <td>${verified}</td>
              <td><small>${dur}</small></td>
              <td style="font-size: 12px; color: ${item.status === 'FAILED' ? 'var(--accent-red)' : 'var(--text-muted)'};">${escapeHtml(item.details || '-')}</td>
            </tr>
          `;
        });
        tbody.innerHTML = html;
      }
    }
  } catch (e) {
    alert("Error opening run details: " + e.message);
  }
}

// 5. DTH REPORTS CONTROLLER
async function loadDthReports() {
  const tbody = document.getElementById('tbody-dth-reports-table');
  if (!tbody) return;

  try {
    const res = await fetch('/api/dth/history?limit=100');
    if (!res.ok) throw new Error("Could not load reports");
    const data = await res.json();
    const runs = data.runs || [];

    // Compute KPI cards
    const totalReports = runs.length;
    let totalCreated = 0;
    let totalSkipped = 0;
    let totalFailed = 0;

    runs.forEach(r => {
      totalCreated += (r.successful_channels || 0);
      totalSkipped += (r.skipped_duplicates || 0);
      totalFailed += ((r.failed_channels || 0) + (r.invalid_channels || 0));
    });

    const totalHandled = totalCreated + totalFailed;
    const rate = totalHandled > 0 ? ((totalCreated / totalHandled) * 100).toFixed(1) + '%' : '100%';

    const elTotal = document.getElementById('dth-reports-stat-total');
    const elCreated = document.getElementById('dth-reports-stat-created');
    const elSkipped = document.getElementById('dth-reports-stat-skipped');
    const elRate = document.getElementById('dth-reports-stat-rate');

    if (elTotal) elTotal.textContent = totalReports;
    if (elCreated) elCreated.textContent = totalCreated;
    if (elSkipped) elSkipped.textContent = totalSkipped;
    if (elRate) elRate.textContent = rate;

    if (runs.length === 0) {
      tbody.innerHTML = `<tr><td colspan="9" style="text-align: center; color: var(--text-muted); padding: 30px;">No DTH execution reports archived yet.</td></tr>`;
      return;
    }

    let html = '';
    runs.forEach(r => {
      const modeBadge = r.mode === 'LIVE' ? 'badge-dth-failed' : 'badge-dth-ready';
      const outcomeBadge = r.status === 'COMPLETED' ? 'badge-dth-success' : 'badge-dth-failed';

      html += `
        <tr>
          <td><strong>#${r.id}</strong></td>
          <td>${escapeHtml(r.run_date || '')} ${escapeHtml(r.start_time || '')}</td>
          <td>${escapeHtml(r.site_name || 'FNB')}</td>
          <td><span class="status-badge ${modeBadge}">${r.mode}</span></td>
          <td>${r.total_channels || 0}</td>
          <td style="color: var(--accent-green); font-weight: 600;">${r.successful_channels || 0}</td>
          <td style="color: var(--accent-amber);">${r.skipped_duplicates || 0}</td>
          <td><span class="status-badge ${outcomeBadge}">${r.status}</span></td>
          <td>
            <div style="display: flex; gap: 6px;">
              <button class="btn btn-secondary btn-sm" onclick="openDthRunDetails(${r.id})">Details</button>
              <a href="/api/dth/reports/${r.id}/csv" target="_blank" class="btn btn-secondary btn-sm" title="Download CSV">CSV</a>
              <a href="/api/dth/reports/${r.id}/json" target="_blank" class="btn btn-secondary btn-sm" title="Download JSON">JSON</a>
            </div>
          </td>
        </tr>
      `;
    });
    tbody.innerHTML = html;
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="9" style="text-align: center; color: var(--accent-red); padding: 25px;">Error loading reports: ${escapeHtml(e.message)}</td></tr>`;
  }
}

// 6. DTH SETTINGS CONTROLLER
async function loadDthSettings() {
  try {
    const res = await fetch('/api/dth/settings');
    if (!res.ok) return;
    const settings = await res.json();

    const setVal = (id, val) => {
      const el = document.getElementById(id);
      if (el) el.value = val !== undefined && val !== null ? val : "";
    };
    const setChk = (id, val) => {
      const el = document.getElementById(id);
      if (el) el.checked = !!val;
    };

    if (settings.default_mode) setVal('dth-set-default-mode', settings.default_mode);
    if (settings.channel_delay_seconds !== undefined) setVal('dth-set-delay', settings.channel_delay_seconds);
    if (settings.max_rows !== undefined) setVal('dth-set-max-rows', settings.max_rows);
    if (settings.max_file_size_mb !== undefined) setVal('dth-set-max-file-mb', settings.max_file_size_mb);
    if (settings.portal_page_timeout !== undefined) setVal('dth-set-page-timeout', settings.portal_page_timeout);
    if (settings.channel_save_timeout !== undefined) setVal('dth-set-save-timeout', settings.channel_save_timeout);
    if (settings.allowed_image_extensions) setVal('dth-set-img-exts', settings.allowed_image_extensions);
    if (settings.max_image_size_kb !== undefined) setVal('dth-set-img-max-kb', settings.max_image_size_kb);
    if (settings.log_level) setVal('dth-set-log-level', settings.log_level);
    if (settings.capture_error_screenshots !== undefined) setChk('dth-set-debug-screenshots', settings.capture_error_screenshots);
  } catch (e) {
    console.error("[DTH UI] Error loading DTH settings:", e);
  }
}

async function saveDthSettings() {
  const payload = {
    default_mode: document.getElementById('dth-set-default-mode')?.value || "DRY_RUN",
    channel_delay_seconds: parseFloat(document.getElementById('dth-set-delay')?.value) || 1.0,
    max_rows: parseInt(document.getElementById('dth-set-max-rows')?.value) || 5000,
    max_file_size_mb: parseInt(document.getElementById('dth-set-max-file-mb')?.value) || 10,
    portal_page_timeout: parseInt(document.getElementById('dth-set-page-timeout')?.value) || 60,
    channel_save_timeout: parseInt(document.getElementById('dth-set-save-timeout')?.value) || 30,
    allowed_image_extensions: document.getElementById('dth-set-img-exts')?.value || ".png, .jpg, .jpeg, .bmp, .webp",
    max_image_size_kb: parseInt(document.getElementById('dth-set-img-max-kb')?.value) || 2048,
    log_level: document.getElementById('dth-set-log-level')?.value || "INFO",
    capture_error_screenshots: document.getElementById('dth-set-debug-screenshots')?.checked ?? true
  };

  try {
    const res = await fetch('/api/dth/settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    if (res.ok) {
      const msg = document.getElementById('dth-settings-status-msg');
      if (msg) {
        msg.style.display = 'block';
        msg.textContent = 'Settings saved successfully.';
        setTimeout(() => { msg.style.display = 'none'; }, 3500);
      }
    } else {
      alert("Error saving DTH settings.");
    }
  } catch (e) {
    alert("Error saving settings: " + e.message);
  }
}

async function resetDthSettings() {
  if (!confirm("Restore default DTH settings?")) return;

  const defaults = {
    default_mode: "DRY_RUN",
    channel_delay_seconds: 1.0,
    max_rows: 5000,
    max_file_size_mb: 10,
    portal_page_timeout: 60,
    channel_save_timeout: 30,
    allowed_image_extensions: ".png, .jpg, .jpeg, .bmp, .webp",
    max_image_size_kb: 2048,
    log_level: "INFO",
    capture_error_screenshots: true
  };

  try {
    const res = await fetch('/api/dth/settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(defaults)
    });
    if (res.ok) {
      loadDthSettings();
      alert("DTH settings restored to defaults.");
    }
  } catch (e) {
    alert("Error resetting settings: " + e.message);
  }
}

// 7. CENTRAL DTH MODULE INITIALIZER & EVENT BINDINGS
function initDthModule() {
  console.log("[DTH UI] Initializing DTH Automation Module...");
  bindDthGlobalEvents();
  initDthTab();
  loadDthDashboard();
}

function bindDthGlobalEvents() {
  // Dashboard Quick Action Buttons
  bindClick('btn-dth-dash-config-sites', () => navigateToTab('dth-sites'));
  bindClick('btn-dth-dash-import', () => navigateToTab('dth-channels'));
  bindClick('btn-dth-dash-reports', () => navigateToTab('dth-reports'));
  bindClick('btn-dth-dash-refresh', () => loadDthDashboard());
  bindClick('btn-dth-dash-view-all-runs', () => navigateToTab('dth-history'));
  bindClick('btn-dth-dash-manage-sites', () => navigateToTab('dth-sites'));
  bindClick('btn-dth-dash-stop', async () => {
    try {
      const res = await fetch('/api/dth/stop', { method: 'POST' });
      const data = await res.json();
      alert(data.message || 'Stop requested.');
    } catch (e) {
      alert("Error: " + e.message);
    }
  });

  // Sites Tab Buttons
  bindClick('btn-dth-add-site', openAddDthSiteModal);
  bindClick('btn-dth-import-ird-sites', importIrdSitesToDth);
  bindClick('btn-dth-refresh-sites', loadDthSitesConfig);
  bindClick('btn-close-modal-dth-site', closeDthSiteModal);
  bindClick('btn-cancel-modal-dth-site', closeDthSiteModal);
  bindClick('btn-save-dth-site', saveDthSite);

  // Toggle Advanced SSH Tunnel Collapsible in Site Modal
  const btnToggleTunnel = document.getElementById('btn-toggle-dth-tunnel-opts');
  if (btnToggleTunnel) {
    btnToggleTunnel.onclick = () => {
      const body = document.getElementById('dth-tunnel-opts-body');
      const chevron = document.getElementById('dth-tunnel-chevron');
      if (body) {
        body.classList.toggle('active');
        if (chevron) {
          chevron.innerHTML = body.classList.contains('active') ? '&#9652;' : '&#9662;';
        }
      }
    };
  }

  // Run Details Inspection Modal
  bindClick('btn-close-dth-run-details', () => {
    const modal = document.getElementById('modal-dth-run-details');
    if (modal) modal.classList.remove('active');
  });
  bindClick('btn-dismiss-dth-run-details', () => {
    const modal = document.getElementById('modal-dth-run-details');
    if (modal) modal.classList.remove('active');
  });

  // Reports Tab
  bindClick('btn-dth-refresh-reports', loadDthReports);

  // Settings Tab
  bindClick('btn-dth-save-settings', saveDthSettings);
  bindClick('btn-dth-reset-settings', resetDthSettings);
}

// Window Global Exports for inline HTML onclick handlers
window.navigateToTab = navigateToTab;
window.openDthRunDetails = openDthRunDetails;
window.testDthSiteFromTable = testDthSiteFromTable;
window.openAddDthSiteModal = openAddDthSiteModal;
window.openEditDthSiteModal = openEditDthSiteModal;
window.deleteDthSite = deleteDthSite;
window.toggleDthSite = toggleDthSite;
window.importIrdSitesToDth = importIrdSitesToDth;

