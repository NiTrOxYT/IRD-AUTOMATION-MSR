# DTH Automation — Independent Dashboard Module Refactoring Plan

**Target Application:** IRD AUTO (`C:\IRD AUTO`)  
**Objective:** Decouple DTH Channel Configuration into a first-class, independent automation product alongside IRD Automation within the same desktop application.  
**Date:** 2026-10-13  
**Status:** In Progress  

---

## 1. Architectural Strategy

The application hosts two distinct automation suites:
1. **IRD Automation:** Daily IRD & MyMenu Synchronization console (`Dashboard`, `Sites Config`, `Run History`, `Integration Test`, `Settings`, `Diagnostics`).
2. **DTH Automation:** Independent DTH Channel Configuration platform (`DTH Dashboard`, `Site Configurations`, `Channel Configuration`, `Execution History`, `Reports`, `Settings`).

Both products share the backend process and low-level infrastructure (Playwright, PuTTY/Plink tunneling, encryption vault, database engine), but maintain 100% data and UI isolation.

---

## 2. Database Model & Isolation Strategy

### 2.1 Dedicated `dth_sites` Table
To prevent modifying, colliding with, or deleting IRD sites, DTH sites are stored in an independent table:

```sql
CREATE TABLE IF NOT EXISTS dth_sites (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    portal_url TEXT DEFAULT '',
    local_port INTEGER DEFAULT 18001,
    site_ip TEXT DEFAULT '',
    site_port INTEGER DEFAULT 80,
    idp_username TEXT DEFAULT '',
    idp_password_encrypted TEXT DEFAULT '',
    enabled INTEGER DEFAULT 1,
    sort_order INTEGER DEFAULT 0,
    notes TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

- Passwords are encrypted using Windows DPAPI (`win32crypt`) with Fernet fallback.
- Active run guard: Deletion of a DTH site is rejected if an active DTH automation batch is targeting it.

### 2.2 Dedicated `dth_settings` Table
Key-value configuration table for DTH runtime parameters:
- `default_mode` (default: `DRY_RUN`)
- `channel_delay_seconds` (default: `1.0`)
- `max_row_count` (default: `5000`)
- `max_file_size_mb` (default: `10`)
- `page_load_timeout` (default: `60`)
- `save_timeout` (default: `30`)
- `debug_screenshots` (default: `true`)

---

## 3. UI Navigation & Independent State

### 3.1 Primary Navigation Switcher
At the top of the sidebar, a prominent module switcher toggles between:
- **IRD Automation**
- **DTH Automation**

### 3.2 DTH Navigation Pages
When **DTH Automation** is active, the sidebar displays:
1. **DTH Dashboard (`tab-dth-dashboard`):** KPI metrics (configured DTH sites, channels processed, success rate, skips, failures), system health, recent runs, quick-action shortcuts.
2. **Site Configurations (`tab-dth-sites`):** Manage DTH sites independently. Add, edit, test connectivity, enable/disable, delete.
3. **Channel Configuration (`tab-dth-channels`):** Upload CSV/XLSX, select image folder, preflight validation, preview table, dry-run, live execution.
4. **Execution History (`tab-dth-history`):** Complete log of DTH runs, row-level results modal, report links.
5. **Reports (`tab-dth-reports`):** Dedicated reports library with per-site metrics, error logs, CSV & JSON download actions.
6. **DTH Settings (`tab-dth-settings`):** DTH-specific timeout, submission delay, file limit, and logging parameters.

---

## 4. API Endpoints Additions (`/api/dth`)

- `GET /api/dth/dashboard/stats`: Aggregated metrics for DTH dashboard.
- `GET /api/dth/sites`: List DTH sites.
- `POST /api/dth/sites`: Add DTH site.
- `GET /api/dth/sites/{site_id}`: Get single DTH site.
- `PUT /api/dth/sites/{site_id}`: Update DTH site.
- `DELETE /api/dth/sites/{site_id}`: Delete DTH site (guarded against active execution).
- `POST /api/dth/sites/{site_id}/test-connection`: Test HTTP/portal connectivity.
- `GET /api/dth/settings`: Retrieve DTH configuration.
- `POST /api/dth/settings`: Save DTH configuration.
