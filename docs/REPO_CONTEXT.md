# FinanzAPP Repository Context

Last reviewed: 2026-08-24.

This file is the persistent project briefing for future chats. Read it before
working on the repository, and keep it updated whenever important behavior,
schema, setup, commands, dependencies, or workflows change.

## Purpose

FinanzAPP is a local/personal finance manager built with Python, NiceGUI,
Pandas and Plotly. It manages:

- user login and registration;
- income, expenses and account transfers;
- expense analysis by sector and date range;
- investment operations and valuation snapshots;
- global net worth charts combining liquidity and investments;
- SQLite backups and restore checks.

The app is not organized as a separate API plus frontend. NiceGUI renders the UI
server-side and view modules call `db.queries` directly.

## Repository Layout

- `main.py`: app entry point, PWA manifest/service worker routes, auth pages,
  root tab shell and initial catalog setup dialog.
- `config.py`: environment-driven private paths, production mode and NiceGUI
  storage secret handling.
- `maintenance.py`: CLI for backup, restore, backup verification and data
  cleanup.
- `db/connection.py`: auth JSON handling, per-user SQLite path resolution,
  schema creation/migration, legacy data migration, startup DB initialization.
- `db/queries.py`: database write/read helpers and core finance/investment
  mutation rules.
- `db/backups.py`: SQLite integrity checks, copy backups, restore validation and
  cleanup archiving.
- `services/analytics.py`: Pandas calculations for liquidity, net worth,
  investment evolution, sector summaries and select-option ordering.
- `services/asset_logos.py`: yfinance website lookup plus DuckDuckGo
  Icons/UI-Avatars logo URL generation for investment asset cards.
- `services/market_prices.py`: yfinance-based quote lookup for investment
  valuation autofill, including same-day-or-previous close and FX conversion
  into EUR.
- `services/bulk_transactions.py`: strict parser/validator for bulk transaction
  `.txt` imports.
- `ui/components.py`: shared UI helpers, formatting, catalog dialogs and
  transaction edit dialogs.
- `ui/styles.py`: global CSS and PWA head tags.
- `ui/views/dashboard.py`: "Saldo Global" tab.
- `ui/views/transactions.py`: "Ingresos y Gastos" tab.
- `ui/views/analysis.py`: "Analisis de gasto" tab.
- `ui/views/investments.py`: "Inversiones" tab.
- `static/icons/`: SVG app icon and browser favicon.
- `private/`: local auth, SQLite DBs, backups and NiceGUI storage. Ignored by
  Git and should be treated as sensitive local data. yfinance runtime cache is
  stored under `private/cache/yfinance`.
- `fa/`: existing local virtual environment. Exclude it from code searches.
- `tmp/` and `.tmp/`: temporary/noisy directories. Exclude them from code
  searches.

At review time the `.git` directory exists but appears empty/non-functional:
`git status` returns "fatal: not a git repository". Do not assume Git commands
are available until this is fixed.

## Runtime And Setup

Dependencies are pinned in `requirements.txt`:

- `nicegui==2.24.2` (there is a commented note for `nicegui==3.12.1`, but the
  active pin is 2.24.2)
- `pandas==2.3.3`
- `plotly==6.5.2`
- `fastapi==0.136.3`
- `uvicorn==0.49.0`
- `yfinance==1.5.2`

Typical local setup:

```powershell
python -m venv fa
.\fa\Scripts\activate
pip install -r requirements.txt
python main.py
```

The app starts at `http://127.0.0.1:8008` with `reload=False`.

This checkout is the development environment. For normal local development,
activate the virtual environment and run `main.py`; the app listens locally on
port `8008`.

If port `8008` is busy on Windows:

```powershell
netstat -ano | findstr :8008
taskkill /F /PID <PID>
```

Running multiple local NiceGUI processes against the same
`FINANZAPP_STORAGE_DIR` can lock files under `private/nicegui` on Windows.
Session cleanup tolerates a `PermissionError` during storage-file deletion, but
the correct development workflow is still to stop the old process before
starting another server on the same app/storage.

Basic syntax validation:

```powershell
python -m compileall -q main.py config.py maintenance.py db services ui
```

There is no automated test suite in the repository at review time. For risky
logic changes, add focused tests if practical or at least run `compileall` plus
manual app checks.

## Production Deployment

Production is a separate server. Do not deploy automatically from Codex. The
user performs production updates manually by replicating the relevant files to
the server and restarting the service.

The current manual production process is:

1. The user runs `subida_prod.bat`.
2. The user opens an SSH session to the server.
3. The user restarts the service:

```bash
sudo systemctl restart finanzapp.service
```

`subida_prod.bat` is not present in this workspace at review time, but its
documented content is:

```bat
@echo off
setlocal

set "SRC=C:\finanzAPP"
set "DST=hduser@192.168.1.49:/var/www/aifunded.es/finanzAPP"
set "PORT=1024"

for /d /r "%SRC%" %%d in (**pycache**) do @if exist "%%d" rmdir /s /q "%%d"

scp -P %PORT% -r ^
 "%SRC%\main.py" ^
 "%SRC%\config.py" ^
 "%SRC%\maintenance.py" ^
 "%SRC%\requirements.txt" ^
 "%SRC%\.env.example" ^
 "%SRC%\.gitignore" ^
 "%SRC%\db" ^
 "%SRC%\services" ^
 "%SRC%\ui" ^
 "%SRC%\static" ^
 "%DST%/"

echo.
echo Subida completada. No se ha subido private, tmp, fa, .git ni **pycache**.
pause
```

When making changes, check whether all modified files are included in that
upload list. If a required production file is outside the batch list, tell the
user clearly in the final response that the deployment batch must also upload
that file or directory. Never upload `private/`, `tmp/`, `fa/`, `.git` or
`__pycache__` unless the user explicitly changes the deployment policy.

## Environment Variables

`config.py` reads:

- `FINANZAPP_ENV`: `prod` or `production` enables production checks.
- `FINANZAPP_STORAGE_SECRET`: NiceGUI storage secret. Required in production and
  must have at least 32 characters.
- `FINANZAPP_PRIVATE_DIR`: default `ROOT/private`.
- `FINANZAPP_DATA_DIR`: default `PRIVATE_DIR/data`.
- `FINANZAPP_AUTH_USERS_FILE`: default `PRIVATE_DIR/auth/usuarios.json`.
- `FINANZAPP_STORAGE_DIR`: default `PRIVATE_DIR/nicegui`.
- `FINANZAPP_BACKUP_DIR`: default `PRIVATE_DIR/backups`.
- `FINANZAPP_BACKUP_ON_STARTUP`: default `1`; set `0` to skip startup backups.
- `FINANZAPP_BACKUP_MIN_HOURS`: default `24`.

yfinance timezone cache is created at `FINANZAPP_PRIVATE_DIR/cache/yfinance` so
quote lookups do not depend on an external user-cache directory.

`.env.example` contains production-style paths under `/var/lib/finanzapp`.
Do not commit a real `.env`.

In development, if no `FINANZAPP_STORAGE_SECRET` exists, `config.get_storage_secret`
creates `private/secrets/storage_secret`.

## Auth And User Data

Auth users are stored in JSON at `private/auth/usuarios.json` by default. Passwords
use PBKDF2-HMAC-SHA256 with per-user salts and 120,000 iterations.

Usernames are normalized to lowercase and must match `^[a-zA-Z0-9_]{3,32}$`.
Passwords must be at least 8 characters and include one uppercase letter and one
digit.

Login lockout is in memory only:

- `MAX_LOGIN_ATTEMPTS = 5`
- `LOGIN_LOCK_SECONDS = 300`

Each user gets a separate SQLite DB:

```text
private/data/finanzas_<username>.db
```

At review time local users are `cesar` and `demo`. Their database integrity
checks pass. Do not document or expose transaction-level personal data unless a
task explicitly requires it.

## Startup Flow

`main.py` runs these steps on import/start:

1. Disables NiceGUI process-pool setup with `nicegui.run.setup = lambda: None`
   because the managed Windows workspace can block multiprocessing pipes. The
   app does not use `ui.run.cpu_bound`.
2. Ensures private directories exist.
3. Configures NiceGUI `Storage.secret` and `Storage.path`.
4. Serves `/static`.
5. Defines PWA `/manifest.json` and `/service-worker.js`; the manifest, global
   head and `ui.run(favicon=...)` use `/static/icons/favicon.svg` as the app
   icon and browser favicon.
6. On direct execution, calls `init_db()` then `ui.run(...)`.

`init_db()`:

- migrates legacy `finanzas*.db*` files from root or root `data/` into
  `FINANZAPP_DATA_DIR`;
- initializes auth JSON;
- migrates legacy data for `cesar` and `demo` when applicable;
- seeds demo data if the `demo` user exists and is empty;
- initializes/migrates every user DB;
- creates due backups through `db.backups.create_due_backups()`.

## Pages And Main Workflows

Routes:

- `/login`: unified authentication card, defaulting to login mode.
- `/register`: same authentication card, defaulting to create-user mode for
  backwards-compatible direct links.
- `/`: authenticated app shell with tabs.
- `/manifest.json`: PWA manifest.
- `/service-worker.js`: simple app-shell cache.

The authenticated header shows a circular user avatar with the user's initial.
The Preferences drawer includes an "Apariencia" section with a dark/light mode
switch. The theme control uses NiceGUI `ui.dark_mode` and stores the current
boolean preference in `app.storage.user["dark_mode"]`.
When the theme changes, the active tab is re-rendered so Plotly charts can be
rebuilt with the shared `aplicar_tema_grafica(fig, is_dark)` helper, which
switches between `plotly_dark` and `plotly_white` with transparent chart
backgrounds and theme-aware axis/grid colors.
The avatar dropdown menu contains "Preferencias", which opens a right-side
slide-over settings hub with drill-down rows for profile, appearance,
notifications, accounts, sectors, brokers and asset types, and "Cerrar sesión"
for logout.

Main tabs:

- `saldo`: net worth summary, liquidity by account, investments pie, and
  branded area charts for liquidity over time and total net worth over time.
- `movimientos`: add income/expense, add account transfer, bulk import `.txt`,
  filters and edit/delete movements. The manual registration card uses a
  segmented control to switch between operations and transfers, a prominent
  amount input, compact data fields and a single full-width save action. The
  movements table
  uses SQL pagination and incremental rendering in 50-row batches as the user
  scrolls.
- `analisis`: persisted date/sector filters, sector expense/income/balance
  summary, breakdown dialog and charts.
- `inversiones`: investment summary, register buy/sell operation, update market
  valuations, edit asset classification, review current
  allocation and current asset balances, open a history modal with operation
  and valuation histories, and open an "Análisis histórico" modal. The
  historical analysis combines buy/sell operations with latest open valuations:
  initial invested money is gross buys, final/current value is gross sells plus
  latest open value, and the modal shows summary cards, grouped bars by asset
  type and an all-assets table including closed positions. The "Registrar operación"
  action opens a dropdown
  with separate flows for operating on an existing asset or adding a new asset.
  Existing-asset operations show current units plus either Yahoo market price
  feedback or the last registered value. New-asset operations use an
  automatic/manual segmented setup: automatic creation validates and confirms
  Yahoo ticker metadata before saving, while manual creation hides ticker/market
  fields and asks only for asset name, broker/entity and asset type. Each active
  asset row can open a large asset detail modal with key metrics, a segmented
  chart selector for position versus unit price, the charted valuation records
  and that asset's buy/sell operation history. Investment operations store
  bought/sold units or shares, and active assets plus histories show known unit
  positions.
  The valuation update dialog orders assets by broker, asset type and descending
  initial value, and shows the last registered value as a read-only reference.

The main pill navigation preserves the spatial order of these tabs. Moving to a
tab farther right makes the new section slide in from the right; moving back to a
tab on the left makes it slide in from the left. Internal refreshes within the
same section do not animate.

Visible numeric formatting uses Spanish separators across the app: `.` for
thousands and `,` for decimals. This is presentation-only; numeric inputs,
database values and import files still use the standard numeric values expected
by Python/browser controls.

New users get `needs_initial_setup=True` and see a three-step catalog setup for
accounts, sectors and brokers. Choosing "Configurar mas adelante" applies the
default catalogs.

The Preferences drawer starts on a grouped settings menu. Accounts, sectors,
brokers and asset types drill down into two-column vault-style catalog grids
with inline add cards; profile, appearance and notifications currently show
placeholder panels.

## Database Schema

Schema is created in `db.connection.init_schema()` and compatibility migrations
run from `ensure_schema_compatible()` whenever a connection is opened through
`conectar_db()`.

Tables:

- `transacciones`: `id`, `fecha`, `fecha_registro`, `tipo`, `descripcion`,
  `cuenta`, `sector`, `importe`, `usuario`.
- `inversiones`: valuation snapshots with `id`, `fecha`, `inversion`,
  `dinero_inicial`, `valor_actual`, `aplicacion`, `tipo_activo`,
  `operacion_id`, `usuario`. `operacion_id` is set only for valuation rows
  generated automatically from a sale operation.
- `historico_inversiones`: realized investment slices with `id`, `fecha`,
  `inversion`, `precio_compra`, `precio_venta`, `comisiones`, `aplicacion`,
  `tipo_activo`, `operacion_id`, `usuario`. `operacion_id` links the realized
  slice to the sale operation so edits/deletes can restore and recalculate the
  open position.
- `operaciones_inversion`: buy/sell operations with `id`, `fecha`,
  `fecha_registro`, `inversion`, `tipo`, `importe`, `unidades`,
  `precio_unitario`, `comisiones`, `cuenta`, `transaccion_id`, `notas`,
  `usuario`.
- `situacion_global`: legacy/unused-looking table with `id`, `fecha`,
  `cantidad`, `ubicacion`, `aplicacion`, `tipo`, `usuario`.
- `brokers`: catalog table, `nombre` primary key.
- `cuentas`: catalog table, `nombre` primary key.
- `sectores`: catalog table, `nombre` primary key.
- `tipos_activo`: catalog table, `nombre` primary key.
- `activos`: canonical asset classification, `inversion`, `aplicacion`,
  `tipo_activo`, `usuario`, primary key `(inversion, usuario)`.
- `activos_cotizacion`: optional quote metadata by `(usuario, inversion)` with
  `ticker_yahoo`, `divisa_cotizacion`, `divisa_valoracion`,
  `auto_update_enabled` and `logo_url`. It is used for optional yfinance
  valuation autofill and persisted asset-card logos; final valuation snapshots
  remain in `inversiones`.
- `preferencias_usuario`: JSON preferences by `(usuario, clave)`.

Supporting indexes include transaction indexes by `(usuario, fecha, id)`,
`(usuario, fecha_registro, id)`, `(usuario, importe, id)` and
`(usuario, tipo, cuenta, sector)` for paginated movement browsing and filters.

`fecha_registro` triggers fill missing values with local date on inserts for
`transacciones` and `operaciones_inversion`. The Python insert helpers usually
set it explicitly to `date.today().isoformat()`.

Catalog seed defaults:

- accounts: `BBVA`, `Santander`, `Revolut`, `Efectivo`
- sectors: `Balance inicial`, `Sueldo`, `Restaurantes`, `Compras`,
  `Transporte`, `Otros`
- brokers: `MyInvestor`, `Trade Republic`, `XTB`
- asset types: `Renta variable`, `Renta fija`, `Activo refugio`,
  `Inmobiliario`, `Criptoactivo`, `Efectivo y monetarios`, `Otros`

## Important Business Rules

Transactions:

- Positive amount means `Ingreso`.
- Negative amount means `Gasto`.
- Amount `0` is rejected.
- Duplicate manual transactions are detected by exact match on date, type,
  description, account, sector, amount and user; the UI asks for confirmation.
- After a manual income/expense transaction is registered, the next manual
  transaction form keeps the same date, account and sector in the user's
  NiceGUI session. Amount and description are reset.
- Closing the account/sector catalog editors from the manual transaction form
  updates only the affected select options and preserves the current form
  inputs.
- Transactions linked to investment operations cannot be edited or deleted from
  the normal transaction edit dialog.
- The movements list queries SQLite directly for count, sum, filters and
  50-row pages; it no longer loads all transaction rows into Pandas before
  rendering the table.

Transfers:

- A transfer uses sector `Traspaso entre cuentas`.
- `insertar_traspaso()` writes two `transacciones` rows: one negative salida
  from origin and one positive entrada to destination.
- Origin and destination must differ in the UI.

Bulk transaction import:

- File must be `.txt`, UTF-8/UTF-8-SIG.
- Header must be exactly `fecha|tipo|descripcion|cuenta|sector|importe`.
- Separator is `|`.
- Date format is `yyyy-mm-dd`.
- Type must be exactly `Ingreso`, `Gasto`, or `Traspaso`.
- Accounts and sectors must already exist in catalogs.
- Ingresos must be positive; gastos must be negative.
- Transfers must use sector `Traspaso entre cuentas` and have a matching line
  with same date, same sector, same absolute amount, opposite sign and different
  account.

Investments:

- There are two concepts:
  - `operaciones_inversion`: real buy/sell operations.
  - `inversiones`: valuation snapshots used for charts and current value.
- Registering a buy/sell operation also creates the linked liquidity movement
  in `transacciones`.
- A sale cannot create a new asset. `Venta` operations are rejected unless the
  asset already exists in `activos` for the user.
- A sale requires a valuation snapshot on or before the operation date and the
  sale amount cannot exceed that snapshot's `valor_actual`.
- A sale splits the latest open valuation snapshot at or before the operation
  date:
  - the sold slice is upserted into `historico_inversiones` with
    `precio_compra = dinero_inicial * (importe_venta / valor_actual)` and
    `precio_venta = importe_venta`; sale `comisiones` are stored separately;
  - the remaining open slice is inserted/updated in `inversiones` on the sale
    date with `dinero_inicial` and `valor_actual` reduced by the sold
    proportions/amounts and `operacion_id` set to the sale operation;
  - because `inversiones` currently has no units column and the operation form
    stores sales by amount, the split is value-proportional rather than
    unit-based.
- Valuation rows generated automatically by sales cannot be deleted from the
  valuation edit dialog or through `eliminar_inversion()`.
- For `Compra`, liquidity movement is negative: `-(importe + comisiones)`.
- For `Venta`, liquidity movement is positive: `importe - comisiones`.
- Sale commissions must be lower than sale amount.
- Buy/sell operations must include `unidades` (shares/participations).
  `precio_unitario` is derived from `importe / unidades`; known unit positions
  are tracked as purchases minus sales and cannot become negative.
- Broker (`aplicacion`) doubles as the liquidity `cuenta` for investment
  operations.
- New operations and valuation inserts/upserts maintain `activos`; operations
  also ensure related catalog entries exist.
- Asset quote metadata is optional and stored separately in
  `activos_cotizacion`. Editing assets can set a Yahoo Finance ticker/ISIN;
  the quote currency is read-only in the editor and is filled by validating the
  ticker against Yahoo Finance. The asset editor can manually synchronize a
  persisted `logo_url`: it uses Yahoo Finance website metadata and DuckDuckGo
  Icons when possible, otherwise a UI-Avatars fallback. Quote metadata remains
  optional.
- When creating a new asset from the investment operation dialog, the user can
  choose automatic Yahoo creation or manual creation. Automatic creation can
  look up the Yahoo ticker metadata, show the resolved logo beside the result
  preview, and fill the new asset name and quote currency before saving the
  operation. The resolved logo URL is stored with the asset quote metadata.
- The valuation update dialog has an optional "Rellenar automáticamente" action.
  It uses configured yfinance tickers and current open units to fill the
  visible "Valor actual" inputs, converts non-EUR prices into EUR via Yahoo FX
  pairs, and still requires the user to save the valuation record manually.
- After operation changes, later valuation snapshot capital (`dinero_inicial`)
  is recalculated from operation history.
- If operation history exists up to a valuation date, snapshot `dinero_inicial`
  is forced from calculated capital rather than user input.
- `activos` rows are deleted only when no related snapshots or operations remain.

Analytics:

- Liquidity is cumulative sum of transaction amounts over time.
- Total net worth by date is cumulative liquidity plus latest valuation for each
  asset at or before that date.
- Latest investment value uses latest row per `inversion`, ordered by `fecha`
  then `id`.
- Current investment pie charts filter latest `inversiones` rows to open
  positions with `valor_actual > 0`; realized rows in `historico_inversiones`
  are excluded from active allocation charts.
- Expense analysis normalizes blank sectors to `Sin sector`.
- Analysis filters are saved as JSON preference key `analisis_gasto_filtros`.

## Maintenance Commands

Create and verify backups for active DBs:

```powershell
python maintenance.py backup
```

Verify all backups:

```powershell
python maintenance.py verify-backups
```

Restore a verified backup:

```powershell
python maintenance.py restore <backup_path> <target_db_name> --replace
```

`target_db_name` must resolve inside `FINANZAPP_DATA_DIR`.

Archive extra files from the data directory while keeping named files:

```powershell
python maintenance.py clean-data finanzas_cesar.db finanzas_demo.db
```

Backups are stored under `private/backups/<db_stem>/<db_stem>_<timestamp>.db` by
default. `backup_database()` runs `PRAGMA integrity_check` before copying and
verifies backup restoration afterward.

## Coding Notes For Future Changes

- Exclude `fa/`, `tmp/`, `.tmp/` and `private/` from broad searches unless the
  task specifically needs them.
- Prefer existing module boundaries:
  - UI construction in `ui/views/*` or `ui/components.py`.
  - Business/database mutations in `db/queries.py`.
  - Schema/auth/path handling in `db/connection.py` and `config.py`.
  - Pandas calculations in `services/analytics.py`.
  - Import parsing/validation in `services/bulk_transactions.py`.
- Use `conectar_db()` for current authenticated-user DB access inside app
  flows; use `conectar_db_usuario(username)` only when explicit user DB access
  is required outside the current NiceGUI session.
- `cargar_datos(tabla, usuario)` returns Pandas DataFrames and enforces an
  allowlist of table names.
- `db.queries` uses f-strings for table/column names only after allowlist checks;
  preserve that pattern if adding dynamic SQL.
- Be careful with investment operation changes because they affect both
  `operaciones_inversion` and linked `transacciones`.
- Avoid deleting catalog values that are in use; existing helpers enforce this.
- Keep PWA head/service-worker behavior in mind when changing startup/routes.
- The codebase currently contains some mojibake-looking strings when displayed
  in this PowerShell environment. Preserve file encoding and avoid unrelated
  text churn unless fixing encoding is the actual task.

## Documentation Maintenance Rule

Update this file in the same work session when any of these change:

- app purpose or major user workflows;
- routes, tabs or UI behavior that affects how the app is used;
- database schema, migrations, table meaning or data paths;
- auth/password/session behavior;
- transaction, transfer, import or investment business rules;
- environment variables, dependencies, setup or run commands;
- backup/restore/maintenance behavior;
- important operational caveats such as Git availability or test coverage.
