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
      if (tabId === 'settings') loadPuTTYInfo();
      if (tabId === 'diagnostics') {
        scanWindows();
        loadPackageHealth();
      }
    });
  });
}

// WEBSOCKET REAL-TIME CONNECTION
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
    setTimeout(initWebSocket, 3000); // Auto reconnect
  };
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
    opt.textContent = `${s.name} (${s.launcher_button})`;
    sel.appendChild(opt);
  });
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

  const nextPort = 18001 + sitesList.length;
  document.getElementById('modal-site-local-port').value = nextPort;
  document.getElementById('modal-site-auth-type').value = "key";
  document.getElementById('modal-site-ssh-host').value = "";
  document.getElementById('modal-site-ssh-port').value = 22;
  document.getElementById('modal-site-ssh-user').value = "";
  document.getElementById('modal-site-session').value = "";
  document.getElementById('modal-site-remote-host').value = "127.0.0.1";
  document.getElementById('modal-site-remote-port').value = 80;
  document.getElementById('modal-site-ssh-key-or-pass').value = "";
  document.getElementById('modal-site-web-url').value = `http://127.0.0.1:${nextPort}`;

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

  document.getElementById('modal-site-local-port').value = site.local_port || 18001;
  document.getElementById('modal-site-auth-type').value = site.auth_type || "key";
  document.getElementById('modal-site-ssh-host').value = site.ssh_host || "";
  document.getElementById('modal-site-ssh-port').value = site.ssh_port || 22;
  document.getElementById('modal-site-ssh-user').value = site.ssh_username || "";
  document.getElementById('modal-site-session').value = site.putty_session || "";
  document.getElementById('modal-site-remote-host').value = site.remote_host || "127.0.0.1";
  document.getElementById('modal-site-remote-port').value = site.remote_port || 80;
  document.getElementById('modal-site-ssh-key-or-pass').value = site.ssh_key_path || site.ssh_password || "";
  document.getElementById('modal-site-web-url').value = site.web_url || site.url || `http://127.0.0.1:${site.local_port || 18001}`;

  document.getElementById('modal-site').classList.add('active');
}

async function saveSiteModal() {
  const siteId = document.getElementById('modal-site-id').value;
  const authType = document.getElementById('modal-site-auth-type').value;
  const keyOrPass = document.getElementById('modal-site-ssh-key-or-pass').value.trim();

  const payload = {
    name: document.getElementById('modal-site-name').value.trim(),
    launcher_button: document.getElementById('modal-site-button').value.trim(),
    url: document.getElementById('modal-site-url').value.trim(),
    idp_username: document.getElementById('modal-site-username').value.trim(),
    idp_password: document.getElementById('modal-site-password').value,
    sort_order: parseInt(document.getElementById('modal-site-order').value) || 0,
    enabled: document.getElementById('modal-site-enabled').checked,
    local_port: parseInt(document.getElementById('modal-site-local-port').value) || 18001,
    auth_type: authType,
    ssh_host: document.getElementById('modal-site-ssh-host').value.trim(),
    ssh_port: parseInt(document.getElementById('modal-site-ssh-port').value) || 22,
    ssh_username: document.getElementById('modal-site-ssh-user').value.trim(),
    putty_session: document.getElementById('modal-site-session').value.trim(),
    remote_host: document.getElementById('modal-site-remote-host').value.trim() || "127.0.0.1",
    remote_port: parseInt(document.getElementById('modal-site-remote-port').value) || 80,
    ssh_key_path: authType === 'key' ? keyOrPass : "",
    ssh_password: authType === 'password' ? keyOrPass : "",
    web_url: document.getElementById('modal-site-web-url').value.trim()
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

    document.getElementById('setting-putty-path').value = settings.putty_path || '';
    document.getElementById('setting-default-local-port').value = settings.default_local_port || 18001;
    document.getElementById('setting-tunnel-timeout').value = settings.tunnel_start_timeout || 30;
    document.getElementById('setting-auto-stop-tunnel').checked = settings.auto_stop_tunnel !== false && settings.auto_stop_tunnel !== 'false';
    document.getElementById('setting-auto-restart-tunnel').checked = settings.auto_restart_tunnel !== false && settings.auto_restart_tunnel !== 'false';

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
    putty_path: document.getElementById('setting-putty-path').value.trim(),
    default_local_port: parseInt(document.getElementById('setting-default-local-port').value) || 18001,
    tunnel_start_timeout: parseInt(document.getElementById('setting-tunnel-timeout').value) || 30,
    auto_stop_tunnel: document.getElementById('setting-auto-stop-tunnel').checked,
    auto_restart_tunnel: document.getElementById('setting-auto-restart-tunnel').checked,
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

async function detectPuTTYExecutable() {
  try {
    const res = await fetch('/api/tunnel/detect', { method: 'POST' });
    const data = await res.json();
    if (data.plink) {
      document.getElementById('setting-putty-path').value = data.plink;
      alert(`PuTTY/Plink detected successfully at:\n${data.plink}`);
    } else {
      alert("Plink executable was not found automatically in standard PATH or directories. Please specify path manually.");
    }
  } catch (e) {
    alert("Detection failed: " + e.message);
  }
}

async function loadPuTTYInfo() {
  try {
    const res = await fetch('/api/tunnel/info');
    const data = await res.json();

    const badgeStatus = document.getElementById('badge-plink-status');
    const badgeVersion = document.getElementById('badge-plink-version');

    if (data.found) {
      badgeStatus.textContent = `✓ ${data.relative_plink || 'FOUND'}`;
      badgeStatus.style.background = 'rgba(34, 197, 94, 0.2)';
      badgeStatus.style.color = '#4ade80';
      badgeVersion.textContent = data.version || 'Release 0.85';
    } else {
      badgeStatus.textContent = '✕ PLINK NOT FOUND';
      badgeStatus.style.background = 'rgba(239, 68, 68, 0.2)';
      badgeStatus.style.color = '#f87171';
      badgeVersion.textContent = 'Expected: tools/putty/plink.exe';
    }
  } catch (e) {
    console.error("Failed loading PuTTY info:", e);
  }
}

async function testPlinkClick() {
  alert("Running 'plink.exe -V' version test...");
  try {
    const res = await fetch('/api/tunnel/test-plink', { method: 'POST' });
    const data = await res.json();
    alert(`PLINK TEST RESULT:\n\nExecutable Path:\n${data.path}\n\nVersion Output:\n${data.version}\n\nResult: ${data.success ? 'PASS' : 'FAIL'}`);
  } catch (e) {
    alert("Plink test failed: " + e.message);
  }
}

async function loadPackageHealth() {
  const container = document.getElementById('package-health-checklist');
  const badgeOverall = document.getElementById('badge-package-overall');

  if (!container) return;
  container.innerHTML = '<div style="color:#94a3b8;">Validating package components...</div>';

  try {
    const res = await fetch('/api/diagnostics/package-health');
    const data = await res.json();

    badgeOverall.textContent = data.overall_status;
    badgeOverall.className = `status-badge ${data.all_ok ? 'badge-no-action' : 'badge-failed'}`;

    let html = '';
    (data.checks || []).forEach(item => {
      const isPass = item.ok;
      const statusColor = isPass ? '#4ade80' : (item.status === 'INFO' ? '#60a5fa' : '#f87171');
      const icon = isPass ? '✓' : (item.status === 'INFO' ? 'ℹ' : '✕');

      html += `
        <div style="background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.08); border-radius: 8px; padding: 12px;">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
            <strong style="font-size: 0.9rem; color: #f8fafc;">${item.name}</strong>
            <span style="font-weight: 700; color: ${statusColor}; font-size: 0.85rem;">${icon} ${item.status}</span>
          </div>
          <div style="font-family: monospace; font-size: 0.8rem; color: var(--accent-cyan); margin-bottom: 4px; word-break: break-all;">
            ${escapeHtml(item.path)}
          </div>
          <div style="font-size: 0.75rem; color: #94a3b8;">
            ${escapeHtml(item.description)}
          </div>
        </div>
      `;
    });

    container.innerHTML = html;
  } catch (e) {
    container.innerHTML = `<div style="color:#f87171;">Health check failed: ${e.message}</div>`;
  }
}

async function testModalTunnel() {
  const siteId = document.getElementById('modal-site-id').value;
  if (!siteId) {
    alert("Please save the site configuration first before running an active SSH tunnel test.");
    return;
  }

  alert(`Initiating SSH reverse tunnel test for Site ID ${siteId}... Please check Integration Test console or wait for notification.`);
  try {
    const res = await fetch(`/api/sites/${siteId}/tunnel/test`, { method: 'POST' });
    const data = await res.json();
    alert(`Tunnel Test Result for ${data.site}:\nStatus: ${data.success ? 'PASS' : 'FAIL'}\nMessage: ${data.message}\nDetails:\n${(data.details || []).join('\n')}`);
  } catch (e) {
    alert("Tunnel test failed: " + e.message);
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

  document.getElementById('btn-start-sync').addEventListener('click', () => {
    const selectedIds = Array.from(document.querySelectorAll('.chk-site-queue:checked')).map(c => parseInt(c.getAttribute('data-id')));
    if (selectedIds.length === 0) {
      alert("Please select at least one site to process.");
      return;
    }
    document.getElementById('confirm-site-count').textContent = selectedIds.length;
    document.getElementById('modal-confirm-real-run').classList.add('active');
  });

  document.getElementById('btn-proceed-real-run').addEventListener('click', () => {
    document.getElementById('modal-confirm-real-run').classList.remove('active');
    startAutomation(false);
  });

  document.getElementById('btn-close-confirm-modal').addEventListener('click', () => {
    document.getElementById('modal-confirm-real-run').classList.remove('active');
  });

  document.getElementById('btn-cancel-confirm-run').addEventListener('click', () => {
    document.getElementById('modal-confirm-real-run').classList.remove('active');
  });

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

  const btnDetectPuTTY = document.getElementById('btn-detect-putty');
  if (btnDetectPuTTY) {
    btnDetectPuTTY.addEventListener('click', detectPuTTYExecutable);
  }

  const btnTestPlink = document.getElementById('btn-test-plink');
  if (btnTestPlink) {
    btnTestPlink.addEventListener('click', testPlinkClick);
  }

  const chkUseCustom = document.getElementById('setting-use-custom-plink');
  if (chkUseCustom) {
    chkUseCustom.addEventListener('change', (e) => {
      const grp = document.getElementById('group-custom-plink');
      if (grp) grp.style.display = e.target.checked ? 'block' : 'none';
    });
  }

  const btnTestModalTunnel = document.getElementById('btn-test-modal-tunnel');
  if (btnTestModalTunnel) {
    btnTestModalTunnel.addEventListener('click', testModalTunnel);
  }

  const btnRunStageTest = document.getElementById('btn-run-stage-test');
  if (btnRunStageTest) {
    btnRunStageTest.addEventListener('click', runIntegrationTestStage);
  }

  const btnStopStageTest = document.getElementById('btn-stop-stage-test');
  if (btnStopStageTest) {
    btnStopStageTest.addEventListener('click', stopIntegrationTest);
  }

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

async function stopIntegrationTest() {
  console.log("Stop test button clicked");
  const liveLogs = document.getElementById('test-live-logs');
  if (liveLogs) {
    const row = document.createElement('div');
    row.className = 'log-row log-warn';
    row.textContent = `[${new Date().toLocaleTimeString()}] Sending stop signal to server...`;
    liveLogs.appendChild(row);
  }
  try {
    await fetch('/api/integration-test/stop', { method: 'POST' });
  } catch (e) {
    console.error("Failed to send stop signal:", e);
  }
}

async function runIntegrationTestStage() {
  console.log("Integration test button clicked");
  const siteSelect = document.getElementById('select-test-site');
  const stageSelect = document.getElementById('select-test-stage');
  const box = document.getElementById('test-output-box');
  const btnRun = document.getElementById('btn-run-stage-test');
  const btnStop = document.getElementById('btn-stop-stage-test');

  const siteId = siteSelect ? siteSelect.value : '';
  const stage = stageSelect ? stageSelect.value : 'backend_test';
  const siteText = siteSelect && siteSelect.options[siteSelect.selectedIndex] ? siteSelect.options[siteSelect.selectedIndex].text : `Site ID ${siteId}`;

  if (!siteId) {
    alert("Please select a site to test.");
    return;
  }

  // 1. Immediate UI Feedback & Diagnostic Logging
  if (btnRun) {
    btnRun.disabled = true;
    btnRun.textContent = 'RUNNING...';
  }
  if (btnStop) {
    btnStop.style.display = 'inline-block';
  }

  const startTime = new Date().toLocaleTimeString();
  box.innerHTML = `
    <div style="font-weight:700; color: #3b82f6; margin-bottom: 8px;">
      TEST STARTED
    </div>
    <div><strong>Target Site:</strong> ${escapeHtml(siteText)}</div>
    <div><strong>Test Stage:</strong> ${escapeHtml(stage.toUpperCase())}</div>
    <div><strong>Status:</strong> <span style="color: #eab308; font-weight:700;">RUNNING...</span></div>
    <div style="margin-top: 10px; font-weight: 600;">Live Execution Logs:</div>
    <div id="test-live-logs" style="margin-top: 6px; font-family: monospace; font-size: 0.85rem; max-height: 250px; overflow-y: auto; background: rgba(0,0,0,0.3); padding: 10px; border-radius: 6px; border: 1px solid rgba(255,255,255,0.1);">
      <div class="log-row log-info">[${startTime}] Integration test button clicked. Requesting stage '${stage}' from backend...</div>
    </div>
  `;

  try {
    const res = await fetch('/api/integration-test/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ site_id: parseInt(siteId), stage: stage })
    });

    if (!res.ok) {
      throw new Error(`HTTP ${res.status}: ${res.statusText}`);
    }

    const data = await res.json();
    let statusColor = data.success ? 'var(--accent-green, #22c55e)' : 'var(--accent-red, #ef4444)';

    let resultHtml = `
      <div style="font-weight:700; font-size: 1.1rem; color: ${statusColor}; margin-bottom: 8px;">
        STATION RESULT: ${data.success ? 'PASS' : 'FAIL'}
      </div>
      <div><strong>Site:</strong> ${escapeHtml(data.site || siteText)}</div>
      <div><strong>Stage:</strong> ${escapeHtml(data.stage || stage)}</div>
      <div style="margin-top: 6px;"><strong>Message:</strong> ${escapeHtml(data.message || '')}</div>
    `;

    if (data.third_line) {
      resultHtml += `<div style="margin-top:4px;"><strong>Line 3 Preview:</strong> <code>${escapeHtml(data.third_line)}</code></div>`;
    }
    if (data.action_point_status) {
      resultHtml += `<div><strong>Action Point Status:</strong> ${escapeHtml(data.action_point_status)}</div>`;
    }

    if (data.details && data.details.length > 0) {
      resultHtml += `<div style="margin-top:10px;"><strong>Diagnostic Steps:</strong><ul style="margin-top:4px; padding-left:20px;">`;
      data.details.forEach(d => {
        resultHtml += `<li>${escapeHtml(d)}</li>`;
      });
      resultHtml += `</ul></div>`;
    }

    if (data.traceback) {
      resultHtml += `<div style="margin-top:10px; color:#ef4444;"><strong>Traceback:</strong><pre style="margin-top:4px; background:rgba(0,0,0,0.5); padding:8px; border-radius:4px; font-size:0.8rem; overflow-x:auto;">${escapeHtml(data.traceback)}</pre></div>`;
    }

    // Retain live log container at bottom
    const currentLiveLogs = document.getElementById('test-live-logs') ? document.getElementById('test-live-logs').innerHTML : '';
    resultHtml += `
      <div style="margin-top: 12px; font-weight: 600;">Execution Log Stream:</div>
      <div id="test-live-logs" style="margin-top: 6px; font-family: monospace; font-size: 0.85rem; max-height: 250px; overflow-y: auto; background: rgba(0,0,0,0.3); padding: 10px; border-radius: 6px; border: 1px solid rgba(255,255,255,0.1);">
        ${currentLiveLogs}
        <div class="log-row ${data.success ? 'log-info' : 'log-error'}">[${new Date().toLocaleTimeString()}] Test completed with status: ${data.success ? 'PASS' : 'FAIL'}</div>
      </div>
    `;

    box.innerHTML = resultHtml;
  } catch (e) {
    box.innerHTML = `
      <div style="font-weight:700; color: var(--accent-red, #ef4444); margin-bottom: 8px;">INTEGRATION TEST ERROR</div>
      <div><strong>Stage:</strong> ${escapeHtml(stage)}</div>
      <div><strong>Error Message:</strong> ${escapeHtml(e.message)}</div>
      ${e.stack ? `<pre style="margin-top:8px; background:rgba(0,0,0,0.4); padding:8px; border-radius:4px; font-size:0.8rem; overflow-x:auto;">${escapeHtml(e.stack)}</pre>` : ''}
    `;
  } finally {
    if (btnRun) {
      btnRun.disabled = false;
      btnRun.textContent = 'RUN STAGE TEST';
    }
    if (btnStop) {
      btnStop.style.display = 'none';
    }
  }
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

