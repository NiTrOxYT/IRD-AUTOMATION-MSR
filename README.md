# IRD AUTO

### Intelligent Restaurant & Hotel Configuration Automation

<p align="center">
  <strong>Automate repetitive hotel F&B configuration workflows with reliability, visibility, and control.</strong>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Platform-Windows-0078D4?style=for-the-badge&logo=windows&logoColor=white" alt="Windows" />
  <img src="https://img.shields.io/badge/Python-3.11%2B-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python" />
  <img src="https://img.shields.io/badge/Automation-Playwright-2EAD33?style=for-the-badge&logo=playwright&logoColor=white" alt="Playwright" />
  <img src="https://img.shields.io/badge/Interface-Desktop-6C63FF?style=for-the-badge" alt="Desktop application" />
</p>

---

## Overview

**IRD AUTO** is a Windows desktop automation application designed to streamline repetitive configuration and synchronization tasks across hotel environments.

It combines browser automation, secure remote connectivity, structured input files, execution monitoring, and audit reporting into a unified workflow.

The goal is simple: reduce manual effort, standardize repetitive operations, and make configuration tasks easier to execute and verify.

## Features

### Automated Configuration

- **IRD Sync Automation** — Automate supported IRD synchronization workflows.
- **DTH Channel Configuration** — Manage supported channel configuration workflows through the portal.
- **Action Point Configuration** — Process food item category assignments from CSV and Excel files.
- **Room Controller Automation** — Provide a dedicated workflow for supported room-controller operations.

### Intelligent Action Point Processing

- Import configuration data from CSV/XLSX files.
- Match food items using their item codes.
- Check whether categories already exist before creating them.
- Inspect subcategories under the correct parent category.
- Expand categories dynamically to access their subcategories.
- Support category-only updates when no subcategory is specified.
- Select the appropriate restaurant configuration.
- Verify execution results and report failures.

### Reliable Browser Automation

- Playwright-based browser interactions.
- Explicit waits for page and element readiness.
- Exact item matching to reduce accidental selection.
- Controlled error handling and recovery.
- Screenshot-based diagnostics for supported execution stages.

### Remote Connectivity

- SSH-based connectivity for supported remote workflows.
- Reverse SSH tunneling through bundled PuTTY/Plink tooling.
- Session and connection handling for remote environments.

### Execution Monitoring & Reporting

- Structured execution logs.
- Run history and execution results.
- Per-item status and failure-stage reporting.
- Screenshots and diagnostic information where available.
- CSV/XLSX-based input workflows and execution reports.

---

## Application Modules

| Module | Purpose |
|---|---|
| IRD Sync | Automate supported IRD synchronization tasks |
| DTH Automation | Execute supported DTH channel configuration workflows |
| Action Point Configuration | Configure food item categories and optional subcategories |
| Room Controller Automation | Automate supported room-controller workflows |

*Module availability and individual capabilities depend on the installed version and target portal.*

## Action Point Configuration Workflow

The Action Point module follows a structured workflow designed to minimize duplicate creation and incorrect item assignments.

```text
CSV / Excel Input
       |
       v
Validate Input Rows
       |
       v
Inspect Existing Categories
       |
       v
Inspect Subcategories
       |
       v
Create Only Confirmed Missing Entries
       |
       v
Search Exact Item Code
       |
       v
Select Item and Wait for UI Update
       |
       v
Select Category
       |
       v
Select Optional Subcategory
       |
       v
Select IRD - DEFAULT
       |
       v
Configure and Verify
       |
       v
Execution Report
```

### Input File

The Action Point workflow supports the following input columns:

| Column | Description |
|---|---|
| `Item Name` | Expected food item name |
| `Item Code` | Exact identifier used to locate the item |
| `Item Price` | Reference value; not modified by category updates |
| `Category` | Target food category |
| `Sub-Category` | Optional target subcategory |
| `Status` | Determines whether the row should be processed |

Only rows with the supported `Category Update` status are processed by this workflow.

### Item Configuration Logic

For each eligible item:

1. Search using the exact item code.
2. Confirm the correct item and select its checkbox.
3. Wait for the portal's configuration interface to update.
4. Select the requested category.
5. If a subcategory is specified, expand the correct parent category and select the matching subcategory.
6. Select `IRD - DEFAULT`.
7. Submit the configuration.
8. Verify the saved result before reporting success.

**Important:** A successful button click is not proof that a configuration was saved. The portal's resulting state must be checked independently.

---

## Technology Stack

| Technology | Role |
|---|---|
| Python | Automation and application logic |
| Playwright | Browser automation |
| PyWebView | Desktop application interface |
| FastAPI | Local application API |
| SQLite | Local structured data storage |
| PuTTY / Plink | SSH connectivity and tunnel management |
| HTML, CSS, JavaScript | Desktop interface and interaction layer |
| Pytest | Automated testing |

The exact dependencies and supported versions should be confirmed against the repository's dependency files.

## Getting Started

### Prerequisites

- Windows environment.
- Python version compatible with the project's dependencies.
- Access to the authorized target portal.
- Required SSH credentials and connectivity for workflows that use remote tunnels.
- The project's configured browser automation dependencies.

### Installation

Clone the repository:

```bash
git clone <YOUR-REPOSITORY-URL>
cd "IRD AUTO"
```

Create and activate a virtual environment:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Install dependencies using the repository's existing dependency file. For example, if `requirements.txt` is present:

```powershell
python -m pip install -r requirements.txt
```

If the project uses a different dependency manager or lockfile, follow the repository's documented setup instead.

### Launch

Use the project's existing launcher or documented entry point. Do not assume a generic Python command is interchangeable with the production desktop launcher.

The local API has previously been configured at:

```text
http://127.0.0.1:18492
```

This address is an example of the application's local configuration, not a guarantee that the service is running.

## Testing

Run the relevant tests using the project's configured test environment.

```powershell
python -m pytest
```

Run a specific test module:

```powershell
python -m pytest tests/test_action_point_item_search_reliability.py -v
```

Automated tests help validate application logic, selectors, workflow sequencing, and failure handling.

**Mocked tests are not equivalent to live portal validation.** Verify critical workflows against an authorized test environment before production use.

## Safety & Reliability

IRD AUTO interacts with live configuration systems. Safe execution is essential.

- **Duplicate protection:** Inspect existing entries before creating categories or subcategories.
- **Fail-closed verification:** An incomplete inspection must not be treated as proof that an entry is missing.
- **Exact matching:** Use the correct item code and verify the corresponding item.
- **Parent-aware selection:** Match subcategories under their intended parent category.
- **Controlled execution:** Use dry-run capabilities where supported before performing live changes.
- **Auditability:** Retain execution reports and diagnostic logs.
- **Failure handling:** Do not report an operation as successful unless its result has been verified.
- **Price protection:** Category updates must not modify item prices.
- **Credential protection:** Keep passwords, tokens, and private keys out of source control and logs.

Before running a large batch, validate a small number of approved items and confirm the saved configuration in the target portal.

## Project Structure

The following is a high-level view of the known Action Point module. The complete repository may contain additional components.

```text
IRD AUTO/
├── app/
│   ├── action_point_automation/
│   │   ├── portal_controller.py
│   │   ├── workflow_runner.py
│   │   ├── models.py
│   │   ├── selectors.py
│   │   ├── validator.py
│   │   └── report_generator.py
│   └── ui/
│       ├── index.html
│       └── app.js
├── tests/
├── logs/
├── reports/
└── README.md
```

Generated logs, reports, screenshots, databases, and configuration files should be excluded from version control when they contain sensitive operational information.

## Roadmap

Potential areas for continued improvement include:

- Faster bulk processing through reduced redundant navigation.
- More reliable portal-state detection.
- Stronger independent post-save verification.
- Improved recovery from transient portal failures.
- More detailed execution timing and performance metrics.
- Expanded regression coverage for category and subcategory handling.
- Better reporting of partial completion and recoverable failures.

These are development priorities, not claims that every feature is already implemented.

## Contributing

Contributions should preserve the application's existing workflows and safety mechanisms.

1. Create a feature branch.
2. Make a focused change.
3. Add or update relevant tests.
4. Run the regression suite.
5. Document any changes to portal selectors, workflow ordering, or configuration behavior.
6. Validate changes in a test environment before production deployment.

## Security

Do not commit:

- Portal credentials.
- SSH passwords or private keys.
- Production configuration exports containing sensitive information.
- Session cookies or authentication tokens.
- Logs or screenshots containing confidential hotel or customer data.

Use environment-specific configuration and appropriate access controls for sensitive settings.

## Disclaimer

IRD AUTO is intended for authorized operational automation. Users are responsible for ensuring that their use complies with applicable organizational policies, access permissions, and target-system requirements.

## License

Add the repository's chosen license before distributing or reusing this software. Until a license is specified, do not assume that the project is open source or that reuse is permitted.

---

<p align="center">
  <strong>IRD AUTO</strong><br/>
  Automate repetitive workflows. Improve consistency. Verify every critical change.
</p>