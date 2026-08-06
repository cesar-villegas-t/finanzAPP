from nicegui import ui


def add_styles():
    ui.add_head_html(
        """
        <link rel="manifest" href="/manifest.json">
        <meta name="theme-color" content="#2563eb">
        <meta name="mobile-web-app-capable" content="yes">
        <meta name="apple-mobile-web-app-capable" content="yes">
        <meta name="apple-mobile-web-app-title" content="FinanzAPP">
        <meta name="apple-mobile-web-app-status-bar-style" content="default">
        <link rel="apple-touch-icon" href="/static/icons/icon-192.png">
        <script>
        if ('serviceWorker' in navigator) {
          window.addEventListener('load', () => {
            navigator.serviceWorker.register('/service-worker.js');
          });
        }
        </script>
        <style>
        body { background: #f6f7fb; color: #111827; }
        .app-shell { max-width: 1440px; margin: 0 auto; padding: 20px 24px 48px; }
        .page-title { font-size: 28px; font-weight: 750; margin-bottom: 16px; }
        .section-title { font-size: 18px; font-weight: 700; margin: 16px 0 8px; }
        .metric-card { min-width: 220px; flex: 1; border-radius: 8px; box-shadow: 0 1px 8px rgba(15, 23, 42, 0.08); }
        .metric-label { font-size: 13px; color: #6b7280; }
        .metric-value { font-size: 24px; font-weight: 760; }
        .chart-card { flex: 1; min-width: 420px; border-radius: 8px; }
        .plotly-chart { width: 100%; height: 420px; min-height: 420px; }
        .plotly-chart-tall { width: 100%; height: 520px; min-height: 520px; }
        .form-card, .table-card { width: 100%; border-radius: 8px; }
        .table-card { overflow-x: auto; }
        .table-header, .table-row {
            display: grid !important;
            width: 100%;
            align-items: center;
            gap: 12px;
            padding: 8px 6px;
        }
        .table-card .table-row > *,
        .table-card .table-header > * {
            display: block;
        }
        .sector-table { grid-template-columns: minmax(180px, 1fr) repeat(3, 112px) 128px; min-width: 760px; }
        .transactions-table { grid-template-columns: 112px 96px minmax(200px, 1fr) 144px 160px 112px 96px; min-width: 1120px; }
        .investments-table { grid-template-columns: minmax(180px, 1fr) 144px repeat(4, 112px) 144px 96px; min-width: 1200px; }
        .investment-ops-table { grid-template-columns: 112px 96px minmax(220px, 1fr) 112px 112px 96px; min-width: 840px; }
        .current-assets-scroll {
            height: 420px;
            min-height: 420px;
            overflow-y: auto;
            overflow-x: hidden;
            width: 100%;
        }
        .current-assets-table {
            display: grid;
            grid-template-columns: minmax(0, 1.4fr) 104px minmax(0, 1fr);
            width: 100%;
            min-width: 0;
            align-items: center;
            gap: 10px;
        }
        .current-assets-table > * {
            min-width: 0;
            padding: 9px 6px;
            border-bottom: 1px solid #eef0f4;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }
        .current-assets-table-header {
            color: #4b5563;
            font-weight: 700;
            position: sticky;
            top: 0;
            z-index: 1;
            background: #ffffff;
        }
        .table-header > *, .table-row > * { width: 100%; min-width: 0; }
        .table-header { color: #4b5563; border-bottom: 1px solid #e5e7eb; }
        .table-row { border-bottom: 1px solid #eef0f4; min-height: 44px; }
        .date-group { margin-top: 16px; padding: 8px 12px; border-left: 4px solid #2563eb; background: #e8eefc; font-weight: 750; width: 100%; }
        .signed-amount-input.amount-positive .q-field__native,
        .signed-amount-input.amount-positive .q-field__label {
            color: #15803d !important;
            font-weight: 750;
        }
        .signed-amount-input.amount-negative .q-field__native,
        .signed-amount-input.amount-negative .q-field__label {
            color: #b91c1c !important;
            font-weight: 750;
        }
        .dialog-card { min-width: 520px; max-width: calc(100vw - 48px); gap: 14px; }
        .wide-dialog { width: 980px; }
        .history-dialog {
            width: min(1320px, calc(100vw - 32px)) !important;
            max-width: calc(100vw - 32px) !important;
            height: min(820px, calc(100vh - 32px)) !important;
            max-height: calc(100vh - 32px) !important;
            overflow: hidden;
            display: flex;
            flex-direction: column;
        }
        .history-dialog-body {
            flex: 1 1 auto;
            min-height: 0;
            overflow: hidden !important;
        }
        .history-dialog-body .q-panel {
            height: 100%;
            min-height: 0;
            overflow: hidden !important;
        }
        .history-tab-panel {
            height: 100%;
            min-height: 0;
            overflow-y: auto !important;
            overflow-x: hidden;
            padding-bottom: 24px;
        }
        .history-table-card {
            overflow: visible !important;
            max-height: none !important;
        }
        .history-table-scroll {
            width: 100%;
            overflow-x: auto;
            overflow-y: clip;
            max-height: none !important;
        }
        .investment-entry-dialog { width: min(1680px, calc(100vw - 48px)) !important; max-width: calc(100vw - 48px) !important; max-height: 92vh; overflow-y: auto; overflow-x: auto; }
        .investment-entry-table { width: 100%; max-width: 100%; overflow: visible; }
        .investment-entry-rows { display: contents; }
        .investment-entry-row {
            display: grid;
            grid-template-columns: 64px minmax(0, 1.35fr) minmax(0, 0.95fr) minmax(0, 0.95fr) minmax(0, 0.8fr) minmax(0, 0.8fr) minmax(0, 0.95fr);
            box-sizing: border-box;
            width: 100%;
            min-width: 1320px;
            align-items: center;
            gap: 10px;
            padding: 8px 6px;
        }
        .investment-entry-row > .investment-entry-cell { width: 100%; min-width: 0; }
        .investment-entry-cell { box-sizing: border-box; padding: 0; }
        .investment-entry-cell > *,
        .investment-entry-cell .q-field,
        .investment-entry-cell .q-field__inner,
        .asset-edit-row > *,
        .asset-edit-row .q-field,
        .asset-edit-row .q-field__inner { width: 100%; min-width: 0; }
        .investment-entry-header .investment-entry-cell,
        .investment-entry-text-cell { padding-left: 12px; padding-right: 12px; }
        .investment-entry-text-cell,
        .asset-edit-row > * {
            overflow: hidden;
            text-overflow: ellipsis;
        }
        .investment-entry-action { display: flex; justify-content: center; padding: 0; }
        .investment-entry-action > * { width: auto; }
        .investment-entry-check-cell { display: flex; justify-content: center; padding: 0; }
        .investment-entry-check-cell > * { width: auto; }
        .investment-entry-header { color: #4b5563; border-bottom: 1px solid #e5e7eb; font-weight: 700; }
        .investment-entry-data { border-bottom: 1px solid #eef0f4; min-height: 64px; }
        .asset-edit-dialog { width: min(1180px, calc(100vw - 48px)) !important; max-width: calc(100vw - 48px) !important; max-height: 92vh; overflow-y: auto; overflow-x: hidden; }
        .asset-edit-row {
            display: grid;
            grid-template-columns: minmax(0, 1.4fr) minmax(0, 1fr) minmax(0, 1fr);
            width: 100%;
            min-width: 0;
            align-items: center;
            gap: 10px;
            padding: 8px 6px;
        }
        .asset-edit-row > * { width: 100%; min-width: 0; }
        .catalog-dialog { width: 720px; max-width: 96vw; max-height: 92vh; overflow-y: auto; }
        .catalog-row {
            display: grid;
            grid-template-columns: minmax(220px, 1fr) 140px 48px;
            width: 100%;
            align-items: center;
            gap: 12px;
            padding: 8px 6px;
            border-bottom: 1px solid #eef0f4;
        }
        .catalog-list { width: 100%; max-height: 56vh; overflow-y: auto; }
        .setup-dialog { width: 820px; max-width: 96vw; max-height: 92vh; overflow-y: auto; }
        .setup-progress { gap: 8px; margin-top: 6px; }
        .setup-step, .setup-step-active {
            flex: 1;
            padding: 10px 12px;
            border-radius: 999px;
            text-align: center;
            font-size: 13px;
            font-weight: 700;
        }
        .setup-step { background: #eef2f7; color: #64748b; }
        .setup-step-active { background: #dbeafe; color: #1d4ed8; }
        .setup-step-card {
            width: 100%;
            border-radius: 14px;
            background: #ffffff;
            box-shadow: 0 1px 10px rgba(15, 23, 42, 0.08);
        }
        .setup-chip-list {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 10px;
            width: 100%;
            margin: 8px 0;
        }
        .setup-chip {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 8px;
            padding: 8px 10px 8px 12px;
            border: 1px solid #dbe3ef;
            border-radius: 12px;
            background: #f8fafc;
        }
        .setup-chip-text {
            min-width: 0;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
            font-weight: 650;
        }
        .setup-chip-remove { color: #dc2626; }
        .analysis-sector-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
            gap: 10px;
            width: 100%;
            max-height: 340px;
            overflow-y: auto;
            padding: 2px;
        }
        .analysis-sector-chip {
            display: flex;
            align-items: center;
            min-width: 0;
            min-height: 44px;
            padding: 6px 10px;
            border: 1px solid #dbe3ef;
            border-radius: 8px;
            background: #f8fafc;
        }
        .analysis-sector-chip:has(.q-checkbox[aria-checked="true"]) {
            border-color: #93c5fd;
            background: #eff6ff;
        }
        .analysis-sector-checkbox,
        .analysis-sector-checkbox .q-checkbox__label {
            width: 100%;
            min-width: 0;
        }
        .analysis-sector-checkbox .q-checkbox__label {
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
            font-weight: 650;
            color: #1f2937;
        }
        .compact-table .q-table__container { box-shadow: none; }
        </style>
        """
    )
