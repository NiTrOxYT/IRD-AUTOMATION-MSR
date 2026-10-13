# DTH Channel Configuration Automation — User & Operational Guide

**Module:** DTH Channel Bulk Automation  
**Application:** IRD AUTO v1.0.0  
**Version:** 1.0.0  
**Date:** 2026-10-13  

---

## 1. Overview

The **DTH Channel Configuration Automation** module enables automated bulk channel provisioning on the ZMP portal via Playwright browser automation. It eliminates manual form data entry while enforcing strict data hygiene, duplicate protection, and mandatory category assignment rules.

---

## 2. Spreadsheet Template & Canonical Schema

You can import channel configurations using either `.csv` (UTF-8) or `.xlsx` (Excel) spreadsheets.

Official sample templates can be downloaded directly from the UI or via API:
- **CSV Template:** `/api/dth/template?format=csv` (stored in `data/templates/dth_channel_template.csv`)
- **Excel Template:** `/api/dth/template?format=xlsx` (stored in `data/templates/dth_channel_template.xlsx`)

### Required Columns

| Column Name | Required | Description | Example |
|---|---|---|---|
| `channel_number` | **Yes** | Unique channel number / LCN. Leading zeros are preserved. | `101` or `005` |
| `name` | **Yes** | Channel display name (1-100 characters). | `Star Sports 1` |
| `osd` | **Yes** | On-Screen Display text (1-50 characters). | `Star Sports 1` |
| `image` | **Yes** | Logo image filename located in your image directory. | `star_sports_1.png` |
| `categories` | **Yes** | Comma-separated list of category names. | `Sports, Entertainment` |

> [!NOTE]
> Column headers are flexible and case-insensitive. Supported header aliases include:
> - `channel_number`: `channel_no`, `channel_num`, `channel`, `lcn`
> - `name`: `channel_name`, `title`
> - `osd`: `osd_name`, `osd_text`
> - `image`: `logo`, `image_file`, `icon`
> - `categories`: `category`, `genre`, `genres`

---

## 3. Mandatory Business & Category Rules

### 3.1 Mandatory Category Rule
Every channel is **automatically assigned to category `all`**, regardless of whether you included `all` in your spreadsheet:
$$\text{Assigned Categories} = \{\text{'all'}\} \cup \{\text{Explicitly Requested Categories}\}$$

- Duplicate category names in a single row are deduplicated case-insensitively.
- Extra whitespace around category names is trimmed automatically.

### 3.2 CREATE ONLY & Duplicate Protection
The automation follows a strict **CREATE ONLY** rule:
- **Never overwrites or deletes:** Existing channels in the portal will never be edited, deleted, or renumbered.
- **Preflight duplicate check:** Duplicate channel numbers or names within the uploaded file are flagged as `INVALID`.
- **Portal duplicate check:** If a channel number or name already exists in the portal table, it is marked `SKIPPED_DUPLICATE` and safely bypassed during live execution.

### 3.3 Safe Image Handling
- Images must reside in a local directory specified in the UI (e.g., `C:\IRD AUTO\data\channel_logos`).
- Path traversal (e.g. `../../secret.png`) and remote URLs (`http://...`) are rejected by the validator.
- Supported image extensions: `.png`, `.jpg`, `.jpeg`, `.bmp`, `.webp`.

---

## 4. Step-by-Step Execution Guide

### Step 1: Open DTH Channels Tab
1. Start the application via `run_app.bat` or `python app\main.py`.
2. In the left navigation sidebar, click **DTH Channels**.

### Step 2: Download Template (Optional)
Click **Template (CSV)** or **Template (XLSX)** in the top action bar to download the starter file.

### Step 3: Choose Source File & Image Directory
1. **Target Site Portal:** Select the destination site (e.g. `FNB`).
2. **Channels Configuration File:** Choose your `.csv` or `.xlsx` file.
3. **Local Image Directory Path:** Enter the folder containing channel logo files (e.g. `C:\IRD AUTO\data\channel_logos`).
4. **Submission Delay:** Set delay between sequential submissions (default: `1.0` second).

### Step 4: Validate & Preview
Click **Validate & Preview** (or **Upload & Inspect File**).  
The system will run preflight checks and display:
- Metric KPI cards: Total, Valid, Invalid, Duplicates.
- Channels table preview with row-level validation badges (`READY`, `INVALID`, `SKIPPED_DUPLICATE`).
- Actionable error explanations for any malformed rows.

### Step 5: Run Dry-Run (Default & Safe)
Click **Run Dry-Run**.  
- Performs complete file parsing, image resolution, and category verification.
- Connects to the portal to scrape existing channels and check for duplicates.
- **ZERO portal mutations:** Does not click Add, fill forms, or click Save.
- Produces downloadable preview reports.

### Step 6: Start Live Configuration
1. When preview results are confirmed, click **START LIVE CONFIGURATION**.
2. A safety confirmation modal will appear detailing the target site and execution parameters.
3. Click **CONFIRM & START LIVE CREATION**.
4. The system will:
   - Establish Playwright browser session.
   - Query portal duplicate baseline.
   - Sequentially fill channel forms, upload logos, select categories, and click Save.
   - Verify each save against portal feedback and reconciliation tables.
   - Update real-time progress bar and metrics.

### Step 7: Emergency Stop & Cancellation
Click **Stop Automation** at any time to gracefully halt execution.  
The system finishes any in-flight channel reconciliation, terminates the browser session, and records partial results without starting subsequent channels.

### Step 8: Download Execution Reports
After execution finishes, click:
- **Download Run CSV** for tabular audit records.
- **Download Run JSON** for complete structured execution metadata.

Reports are permanently stored under `reports/dth/<YYYY-MM-DD>_dth_run_<run_id>.csv` and `.json`.

---

## 5. REST API Reference

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/dth/template` | Download CSV or XLSX template (`?format=csv` or `?format=xlsx`). |
| `POST` | `/api/dth/upload` | Upload `.csv` or `.xlsx` file (`multipart/form-data`). |
| `POST` | `/api/dth/validate` | Preflight validation returning preview items and errors. |
| `POST` | `/api/dth/execute` | Start `DRY_RUN` or `LIVE` execution (`authorized=True` required for live). |
| `GET` | `/api/dth/status` | Current execution status, active channel, and progress percentage. |
| `POST` | `/api/dth/stop` | Request graceful cancellation. |
| `GET` | `/api/dth/history` | List of past DTH execution runs. |
| `GET` | `/api/dth/runs/{run_id}` | Detailed summary and row-level results for a run. |
| `GET` | `/api/dth/reports/{run_id}/csv` | Download CSV report for a run. |
| `GET` | `/api/dth/reports/{run_id}/json` | Download JSON report for a run. |
| `GET` | `/api/dth/categories` | List available portal categories. |
| `GET` | `/api/dth/selectors` | View active DTH portal selectors. |
| `POST` | `/api/dth/selectors` | Override a portal selector dynamically. |
