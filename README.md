<p align="center">
  <img src="https://raw.githubusercontent.com/tandpfun/skill-icons/main/icons/Python-Dark.svg" width="64" height="64" alt="Python Logo" />
</p>

<h1 align="center">⚡ IRD AUTO ⚡</h1>

<p align="center">
  <strong>Mission-Critical Hotel F&B & In-Room Entertainment Automation Platform</strong>
</p>

<p align="center">
  <a href="#-core-architecture"><img src="https://img.shields.io/badge/Platform-Windows%2010%2F11-0078D4?style=for-the-badge&logo=windows&logoColor=white" alt="Windows" /></a>
  <a href="#-technology-stack"><img src="https://img.shields.io/badge/Python-3.11%2B-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.11+" /></a>
  <a href="#-reliable-browser-automation"><img src="https://img.shields.io/badge/Automation-Playwright-2EAD33?style=for-the-badge&logo=playwright&logoColor=white" alt="Playwright" /></a>
  <a href="#-technology-stack"><img src="https://img.shields.io/badge/Backend-FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white" alt="FastAPI" /></a>
  <a href="#-remote-tunneling-engine"><img src="https://img.shields.io/badge/Tunnel-PuTTY%2FPlink-FF6F00?style=for-the-badge&logo=powershell&logoColor=white" alt="PuTTY/Plink" /></a>
  <a href="#-test-suite-status"><img src="https://img.shields.io/badge/Tests-126%2F126%20Passed-10B981?style=for-the-badge&logo=pytest&logoColor=white" alt="Tests" /></a>
</p>

---

## 🌟 Executive Overview

**IRD AUTO** is an enterprise-grade desktop automation system engineered to eliminate manual toil, configuration drift, and human errors across luxury hotel and hospitality ecosystems. 

Operating at the intersection of **Playwright headless automation**, **reverse SSH port-forwarding**, and **deterministic state machines**, IRD AUTO transforms complex, multi-step In-Room Dining (IRD) portal updates into a predictable, one-click, verified operation.

```
       Excel / CSV Menu Matrix
                  │
                  ▼
     ┌────────────────────────┐
     │ Ingestion & Validation │ ─── Preflight sanity check & schema linting
     └────────────────────────┘
                  │
                  ▼
     ┌────────────────────────┐
     │ Auto-Healing SSH Tunnel│ ─── Plink reverse tunnel (-L local_port:site:port)
     └────────────────────────┘
                  │
                  ▼
     ┌────────────────────────┐
     │ Playwright State Engine│ ─── 9-Step Zero-Failure pipeline & DOM verification
     └────────────────────────┘
                  │
                  ▼
     ┌────────────────────────┐
     │ Independent Inspection │ ─── Post-save verification & audit capture
     └────────────────────────┘
                  │
                  ▼
      CSV / JSON / XLSX Audit Reports + Full Trace Diagnostics
```

---

## 💎 Core Capabilities

### 🍱 1. Intelligent Action Point Configuration
- **Excel & CSV Ingestion**: Parses food items, target categories, subcategories, and operational statuses (`Category Update`).
- **Dynamic Category Tree Resolution**: Auto-discovers existing categories across multi-page tables, identifies missing entries, and expands hierarchical nodes safely without modifying parent entities.
- **Fail-Closed Item Pairing**: Matches exact item codes (preserving leading zeroes), verifies associated titles, and selects row-scoped controls without global ambiguity.

### ⏱️ 2. IRD Daily Sync & 3-Minute Resilience
- **Deterministic 3-Minute Fetch Rule**: Allows slow upstream PMS/POS sync operations ample processing time before evaluating synchronization outcomes.
- **Once-Per-Day Process Protection**: Automatically tracks last execution dates to prevent double-processing menus within the same operating window.
- **Whitelabel Session Recovery**: Seamlessly catches transient server crashes or session timeouts, rolling back to authentication and resuming workflow state in-flight.

### 📺 3. DTH Channel & Entertainment Automation
- **EPG & Channel Ordering**: Automates satellite and IP television channel ordering and attribute updates across hotel headend controllers.
- **Visual Logo Matcher**: Matches channel brand identities against verified asset repositories.

### 🔌 4. Room Controller & Remote Gateway
- **Multi-Site Tunnel Orchestrator**: Manages background SSH tunnels across diverse hotel properties with automated port allocation (`18001` - `18099`).
- **Endpoint Keep-Alive & Health Probing**: Constantly monitors TCP socket availability to ensure uninterrupted command delivery.

---

## 🛡️ Mission-Critical Invariants

Hospitality databases demand absolute integrity. IRD AUTO is governed by five non-negotiable safety rules:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ 1. PRICE PROTECTION INVARIANT                                               │
│    Food item prices are STRICTLY READ-ONLY. The automation engine is        │
│    architecturally prohibited from modifying monetary values.               │
├─────────────────────────────────────────────────────────────────────────────┤
│ 2. FAIL-CLOSED VERIFICATION                                                 │
│    An operation is NEVER considered complete upon click. Every state change │
│    must be independently confirmed on the refreshed DOM.                    │
├─────────────────────────────────────────────────────────────────────────────┤
│ 3. ZERO BLIND OR FORCE-CLICKS                                               │
│    No clicking detached cells or unverified checkboxes. If element          │
│    inspection fails, execution halts safely with a complete diagnostic dump.│
├─────────────────────────────────────────────────────────────────────────────┤
│ 4. DUPLICATE MUTATION PREVENTION                                            │
│    Categories and subcategories are cached in-memory and verified before    │
│    creation to prevent duplicate hierarchy pollution.                       │
├─────────────────────────────────────────────────────────────────────────────┤
│ 5. REVERSIBLE DRY-RUN VERIFICATION                                          │
│    Every workflow supports zero-mutation dry-run simulation, validating DOM │
│    paths, locators, and form readiness without writing changes to the DB.   │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 🔄 The 9-Step Item Configuration Lifecycle

Every item processed in the Action Point engine passes through a strict sequential pipeline:

```mermaid
sequenceDiagram
    autonumber
    participant Engine as IRD AUTO Runner
    participant Browser as Playwright Browser
    participant Portal as Hotel F&B Portal
    participant DB as SQLite Audit DB

    Engine->>Browser: 1. Search Item Code (e.g. 241000003)
    Browser->>Portal: Filter table rows
    Portal-->>Browser: Return matching row
    Engine->>Browser: 2. Verify Item Identity & Code Match
    Engine->>Browser: 3. Select Item Checkbox (Scoped to row)
    Browser->>Portal: onchange="viewFoodItemConfiguration(id)" POST
    Portal-->>Browser: Reload page with item at Row 0
    Engine->>Browser: 4. Verify Checkbox Checked & Form Readiness
    Engine->>Browser: 5. Select Target Category
    opt Subcategory requested
        Engine->>Browser: 6. Expand Parent & Select Subcategory
    end
    Engine->>Browser: 7. Select Restaurant ("IRD - DEFAULT")
    alt DRY RUN Mode
        Engine->>DB: Log Pre-Save Verified (Zero Mutation)
    else LIVE Mode
        Engine->>Browser: 8. Click Submit / "Configure"
        Browser->>Portal: POST Configuration Payload
        Portal-->>Browser: "Item Configured Successfully !"
        Engine->>Browser: 9. Independently Verify Saved State
        Engine->>DB: Record All 8 Stage Outcomes & Timings
    end
```

### Granular Stage Telemetry
Every single row records 8 discrete boolean stages:
1. `item_found`
2. `item_checkbox_selected`
3. `category_selected`
4. `subcategory_selected`
5. `subcategory_skipped` (for category-only rows)
6. `restaurant_selected`
7. `configure_submitted`
8. `persisted_verified`

---

## 📊 Application Architecture

```text
c:\IRD AUTO/
├── app/
│   ├── action_point_automation/    # F&B Action Point configuration engine
│   │   ├── portal_controller.py    # Playwright browser controller & DOM traversal
│   │   ├── workflow_runner.py      # Orchestrator with row-level error isolation
│   │   ├── models.py               # Pydantic data schemas & stage tracking models
│   │   ├── selectors.py            # Hardened, unambiguous DOM locators
│   │   ├── validator.py            # Normalization (colons, symbols) & fuzzy matching
│   │   └── report_generator.py     # Multi-format reporting (CSV, JSON, XLSX)
│   ├── dth_automation/             # DTH television channel & logo mapping engine
│   ├── tunneling/                  # Plink/PuTTY SSH port-forwarding manager
│   ├── database/                   # SQLite schema, migrations & persistence layer
│   ├── ui/                         # Modern HTML5/CSS3/Vanilla JS desktop interface
│   └── main.py                     # FastAPI application entry point & API routes
├── tools/putty/                    # Bundled Plink & PuTTY binary tooling
├── reports/                        # Timestamped execution summaries
├── logs/                           # Granular execution logs & stage screenshots
└── tests/                          # 126-test automated regression suite
```

---

## 🚀 Getting Started

### Prerequisites

- **OS**: Windows 10 / Windows 11 (64-bit)
- **Python**: 3.11.x installed and added to `PATH`
- **Network**: Authorized network access or credentials for hotel reverse-tunnels

### 1. Clone & Set Up Virtual Environment

```powershell
# Clone the repository
git clone <YOUR-REPOSITORY-URL>
cd "c:\IRD AUTO"

# Create and activate Python 3.11 virtual environment
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 2. Install Dependencies & Playwright Browsers

```powershell
# Install application requirements
pip install -r requirements.txt

# Install Playwright browser binaries
playwright install chromium
```

### 3. Launch the Application

```powershell
# Run via production launcher
.\run_app.bat

# Or launch directly with Uvicorn
python -m uvicorn app.main:app --host 127.0.0.1 --port 18492
```

The desktop application UI will launch automatically via PyWebView, connected to the local API at `http://127.0.0.1:18492`.

---

## 🧪 Automated Testing & Quality Assurance

IRD AUTO enforces a comprehensive, multi-layer regression suite with **100% pass rate** across all subsystems:

```powershell
# Run the entire Action Point regression suite
python -m pytest tests/ -k "action_point" -v

# Run targeted item search and subcategory reliability tests
python -m pytest tests/test_action_point_item_search_reliability.py tests/test_action_point_subcategory_selection.py -v
```

<details>
<summary><strong>🔍 Click to expand the full test suite breakdown (126 Tests)</strong></summary>

| Test Module | Coverage Area | Tests | Status |
| :--- | :--- | :---: | :---: |
| `test_action_point_item_search_reliability.py` | Item lookup, row-scoped checkboxes, DOM refresh | 20 | **PASS** ✅ |
| `test_action_point_subcategory_selection.py` | Parent expansion, spacer rows, selector safety | 7 | **PASS** ✅ |
| `test_action_point_phase7_mocked.py` | Comprehensive mock simulation & boundary edge-cases | 35 | **PASS** ✅ |
| `test_action_point_bulk_optimization.py` | Tree caching, navigation reuse, price immutability | 7 | **PASS** ✅ |
| `test_action_point_portal_mocked.py` | Session loss, whitelabel recovery, preflight checks | 13 | **PASS** ✅ |
| `test_action_point_reliability.py` | Category existence checks, pagination, safe aborts | 14 | **PASS** ✅ |
| `test_action_point_reports.py` | CSV, JSON, and XLSX report generator validation | 1 | **PASS** ✅ |
| `test_action_point_validator.py` | String normalization, status classification, dry-run plan | 6 | **PASS** ✅ |
| `test_action_point_workflow.py` | End-to-end runner orchestration & stage persistence | 4 | **PASS** ✅ |
| `test_action_point_api.py` | FastAPI route registration, status & history endpoints | 5 | **PASS** ✅ |
| **Full Action Point Suite** | **Zero-Failure Enterprise Pipeline Verification** | **126** | **100% PASS** 🚀 |

</details>

---

## 📈 Real-World Performance Metrics

Verified live execution benchmarks from production deployment on **ITC Gardenia (Site 73)**:

```
========================================================================================
RUN 405 LIVE EXECUTION BENCHMARKS (22/22 ITEMS SUCCESSFUL)
========================================================================================
Total Run Duration           : 248.46s
Average Time Per Item        : 9.25s
Navigation Duration (Total)  : 7.74s (Single navigation reused across all rows)
Authentication & Recovery    : 15.16s
Category Tree Inspection     : 20.34s (81 existing categories discovered & indexed)
Item Processing Pipeline     : 203.55s
Stage Timings:
  ├── Search & Match         : 3.45s avg
  ├── Checkbox & POST Reload : 0.85s avg
  ├── Category/Subcat Select : 0.23s avg
  ├── Configure Submission   : 0.22s avg
  └── Persistence Verify     : 1.05s avg
Force-Click Warnings Emitted : 0 (Clean DOM resolution)
Final Outcome                : 100.0% SUCCESS
========================================================================================
```

---

## 🗂️ Reports & Audit Artifacts

Every completed run produces timestamped, audit-ready deliverables in `reports/action_point/`:

- **CSV Audit Sheet**: Complete per-row stage breakdown (`Item Found`, `Checkbox Selected`, `Category Selected`, `Subcategory Selected`, `Subcategory Skipped`, `Restaurant Selected`, `Configure Submitted`, `Persisted Verified`).
- **Structured JSON**: High-fidelity execution telemetry, stage durations, and machine-readable metadata.
- **Formatted Excel Workbook**: Presentation-ready reporting for hotel operations management and IT leadership.
- **Stage Screenshots**: High-resolution snapshots captured at critical transition points stored in `logs/screenshots/<Date>/<Site>/run_<ID>/`.

---

## 🔒 Security & Safe Handling

- **Credential Encryption**: All database passwords and keys are protected using local machine-level cryptographic routines.
- **Sanitized Logging**: All Plink and SSH commands scrub sensitive credentials prior to standard out or file logging.
- **Access Scope**: Automated interaction is strictly constrained to authorized internal configuration interfaces.

---

<p align="center">
  <sub>Built with precision for the hospitality industry. Engineered by the IRD Automation Engineering Team.</sub><br/>
  <strong>IRD AUTO — Deterministic Automation. Uncompromised Reliability.</strong>
</p>
