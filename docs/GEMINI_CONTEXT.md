# FinanzAPP Context For Gemini

## Objective

This document gives Gemini enough project context to help with product ideas,
feature design, UX review, prioritization and implementation planning for
FinanzAPP.

FinanzAPP is a personal finance web app for local/private use. It is built to
manage day-to-day finances and investment tracking in one place:

- income, expenses and account transfers;
- expense analysis by sector and date range;
- investment operations, valuation snapshots and active positions;
- global net worth charts combining cash and investments;
- user login, local per-user data and backups.

The app is not a public SaaS product. It is a private finance tool, so any
suggestion should prioritize clarity, correctness, privacy, maintainability and
low operational complexity.

## Tech Stack

- Python
- NiceGUI `2.24.2` for the server-rendered UI
- SQLite for persistence
- Pandas for calculations and transformations
- Plotly for charts
- FastAPI/Uvicorn as the underlying web runtime through NiceGUI

There is no separate frontend app and no REST API layer. NiceGUI renders the UI
server-side. View modules call `db.queries` directly.

The app runs locally at:

```powershell
python main.py
```

Default URL:

```text
http://127.0.0.1:8008
```

Basic validation command:

```powershell
python -m compileall -q main.py config.py maintenance.py db services ui
```

## Repository Structure

```text
main.py                  App entry point, routes, auth pages, tab shell, PWA routes
config.py                Environment/private path configuration
maintenance.py           Backup/restore/cleanup CLI
requirements.txt         Pinned dependencies

db/
  connection.py          SQLite schema, migrations, auth JSON, per-user DB paths
  queries.py             Database read/write helpers and business rules
  backups.py             Backup, restore validation and integrity checks

services/
  analytics.py           Pandas calculations for charts, summaries and options
  bulk_transactions.py   Strict .txt bulk transaction parser/validator

ui/
  styles.py              Global CSS and PWA head tags
  components.py          Shared UI helpers and dialogs
  views/
    dashboard.py         "Saldo Global" tab
    transactions.py      "Ingresos y Gastos" tab
    analysis.py          "Analisis de gasto" tab
    investments.py       "Inversiones" tab

static/icons/            PWA icons
docs/                    Project documentation and context notes
private/                 Ignored local private auth, DBs, backups, storage
fa/                      Local virtual environment
tmp/, .tmp/              Temporary/noisy directories
```

Do not base product ideas on files under `private/`; they contain sensitive
personal finance/auth data and are ignored by Git.

## User Model And Data Model

The app supports multiple local users. Each user has a separate SQLite database:

```text
private/data/finanzas_<username>.db
```

Authentication users are stored in:

```text
private/auth/usuarios.json
```

Passwords use PBKDF2-HMAC-SHA256 with salts. This is a local/private app, not an
enterprise auth system.

Main tables:

- `transacciones`: income, expenses and transfers.
- `operaciones_inversion`: real investment buy/sell operations.
- `inversiones`: investment valuation snapshots used for charts/current value.
- `historico_inversiones`: realized investment slices from sales.
- `activos`: canonical asset classification by asset name/user.
- `cuentas`, `sectores`, `brokers`, `tipos_activo`: catalog tables.
- `preferencias_usuario`: JSON preferences.
- `situacion_global`: legacy/unused-looking table.

## App Sections

### Login And Registration

Routes:

- `/login`
- `/register`
- `/`

New users can go through an initial catalog setup flow for accounts, sectors and
brokers. They can also skip and use default catalogs.

### Saldo Global

Implemented in `ui/views/dashboard.py`.

Purpose:

- global net worth overview;
- current liquidity by account;
- current investment value;
- investment allocation pie;
- liquidity evolution over time;
- total net worth evolution over time.

Useful future idea space:

- clearer month-over-month movement;
- net worth milestones;
- warnings when a large change is due to missing valuation updates;
- cash vs investment trend explanations.

### Ingresos y Gastos

Implemented in `ui/views/transactions.py`.

Purpose:

- manually add income/expense;
- register transfers between accounts;
- bulk import transactions from `.txt`;
- filter, edit and delete movements;
- edit account and sector catalogs.

Important rules:

- positive amount is `Ingreso`;
- negative amount is `Gasto`;
- amount `0` is rejected;
- transfers create two rows: one negative origin and one positive destination;
- investment-linked transactions cannot be edited/deleted from the normal
  transaction dialog.

Bulk import:

- file must be `.txt`;
- UTF-8 or UTF-8-SIG;
- header must be exactly `fecha|tipo|descripcion|cuenta|sector|importe`;
- separator is `|`;
- date format is `yyyy-mm-dd`;
- type must be `Ingreso`, `Gasto` or `Traspaso`;
- accounts and sectors must already exist.

Useful future idea space:

- import previews and reconciliation;
- recurring transaction detection;
- suggested sector classification;
- duplicate review UI;
- monthly budget views.

### Analisis de Gasto

Implemented in `ui/views/analysis.py`.

Purpose:

- analyze spending/income by date range and sector;
- show sector summaries;
- open breakdown dialogs;
- display charts;
- persist selected filters in user preferences.

Useful future idea space:

- budget vs actual;
- trend comparisons against previous periods;
- anomaly detection;
- subscriptions/fixed-cost detection;
- category cleanup suggestions.

### Inversiones

Implemented in `ui/views/investments.py`.

Purpose:

- investment summary metrics;
- register buy/sell operations;
- update market valuations;
- edit asset classification;
- edit brokers/types;
- review current allocation;
- review current active asset rows;
- open general history modal;
- open asset detail modal from each active asset row.

Investment concepts:

- `operaciones_inversion` are real operations: buy/sell.
- `inversiones` are valuation snapshots: current/dated market value.
- Active asset values come from the latest `inversiones` row per asset.
- The global investment evolution chart calculates the latest known valuation
  per asset for each date.

Current investment workflow:

1. Register a buy or sell operation.
2. The app creates a linked liquidity transaction.
3. Periodically update valuations for active assets.
4. Charts use the valuation snapshots.
5. Sales create/update realized history and reduce the open valuation slice.

Important investment rules:

- A sale cannot create a new asset.
- A sale requires a valuation snapshot on or before the operation date.
- Sale amount cannot exceed the latest snapshot value.
- Sale commissions must be lower than sale amount.
- Broker (`aplicacion`) is also used as the liquidity account for the operation.
- Buy liquidity movement is negative: `-(importe + comisiones)`.
- Sell liquidity movement is positive: `importe - comisiones`.
- Later valuation snapshot capital is recalculated after operation changes.
- If operation history exists up to a valuation date, snapshot capital is forced
  from calculated operation capital.
- Valuation rows automatically generated by sales cannot be deleted from the
  valuation edit dialog.

Units/shares:

- Buy/sell operations can store `unidades` and derived `precio_unitario`.
- `precio_unitario = importe / unidades` when units are provided.
- Known unit position is purchases minus sales.
- Known unit positions cannot become negative.
- Once an asset has any operation with units, all saved operations for that
  asset must include units.
- Old operations without units may still exist until edited/backfilled.

Asset detail modal:

- opened from the graph icon in the active assets table;
- shows a chart for that asset;
- shows valuation records by date;
- shows the asset's operation history;
- shows unit position information when available.

Useful future idea space:

- cost basis and unrealized gain per unit;
- FIFO/LIFO or average-cost realized performance;
- dividends/interests as a first-class workflow;
- asset-level notes and tags;
- broker/account reconciliation;
- alerts for stale valuations;
- target allocation and rebalancing suggestions;
- portfolio performance excluding contributions;
- import operations from broker CSVs.

## Styling And UX Principles

The current app is a utility/dashboard-style finance tool. Good ideas should
favor:

- dense but readable layouts;
- fast repeated workflows;
- clear tables and filters;
- low visual noise;
- restrained colors;
- actionable charts;
- simple dialogs for create/edit flows;
- warnings before destructive or high-impact operations.

Avoid ideas that turn the app into a marketing-style product page. The first
screen after login is the working app, not a landing page.

NiceGUI/Quasar patterns currently used:

- tabs for main sections and history views;
- cards for metric blocks and chart/table containers;
- dialogs for edits and detail views;
- Plotly charts for visualizations;
- custom CSS in `ui/styles.py` for grid tables and modal layout.

## Operational Constraints

Private finance data lives under `private/`. Avoid exposing transaction-level
details in docs or examples. When proposing analyses, prefer aggregate counts,
trends and summaries.

There is currently no automated test suite. For implementation work, the minimum
validation is:

```powershell
python -m compileall -q main.py config.py maintenance.py db services ui
```

For risky data/business-rule changes, propose focused tests or at least manual
checks with the demo user.

Production deployment is manual. The user copies code to a separate server and
restarts a service. Do not assume automatic deployment.

The documented production upload list includes:

- `main.py`
- `config.py`
- `maintenance.py`
- `requirements.txt`
- `.env.example`
- `.gitignore`
- `db/`
- `services/`
- `ui/`
- `static/`

It does not upload `private/`, `tmp/`, `fa/`, `.git` or `__pycache__`.

## How Gemini Should Help

Gemini can be most useful by helping with:

- product ideation;
- prioritizing features by impact and complexity;
- improving workflows;
- identifying missing finance views;
- designing tables, charts and dialogs;
- writing user stories and acceptance criteria;
- spotting confusing terminology;
- proposing low-risk implementation approaches;
- suggesting manual QA checklists.

When proposing a feature, Gemini should include:

1. User problem.
2. Proposed workflow.
3. Where it fits in the current app.
4. Data needed.
5. Schema impact, if any.
6. UI impact.
7. Edge cases.
8. Privacy/security considerations.
9. Suggested implementation order.
10. Manual validation checklist.

## Good Feature Proposal Format

Use this structure for future proposals:

```markdown
## Feature: <name>

### Problem
...

### Proposed UX
...

### Data Model
...

### Implementation Notes
...

### Edge Cases
...

### Validation
...

### Risk
Low / Medium / High, with reason.
```

## Important Caveats

- Do not suggest reading or sharing raw private data unless the user explicitly
  asks and there is a clear need.
- Be careful with investment logic; it affects both investment operations and
  linked liquidity transactions.
- Be careful with schema changes; `db.connection.ensure_schema_compatible()`
  handles migrations.
- Preserve the existing module boundaries.
- Prefer incremental features over large rewrites.
- Prefer clear financial semantics over flashy visuals.
- If a suggestion depends on a finance/accounting assumption, state it clearly.

