from nicegui import ui


def add_styles():
    ui.colors(
        primary="#2563EB",
        secondary="#94A3B8",
        positive="#10B981",
        negative="#F43F5E",
    )
    ui.add_head_html(
        """
        <link rel="manifest" href="/manifest.json">
        <link rel="icon" type="image/svg+xml" href="/static/icons/favicon.svg">
        <link rel="shortcut icon" type="image/svg+xml" href="/static/icons/favicon.svg">
        <meta name="theme-color" content="#2563EB">
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
        :root {
            --color-bg-base: #F8FAFC;
            --color-bg-surface: #FFFFFF;
            --color-text-main: #1E293B;
            --color-text-muted: #64748B;
            --color-primary: #2563EB;
            --color-secondary: #94A3B8;
            --color-interactive: #EFF6FF;
            --color-positive: #10B981;
            --color-positive-bg: #ECFDF5;
            --color-negative: #F43F5E;
            --color-negative-bg: #FFF1F2;
            --chart-cat-1: #3B82F6;
            --chart-cat-2: #06B6D4;
            --chart-cat-3: #8B5CF6;
            --chart-cat-4: #F97316;
            --chart-cat-5: #F43F5E;
            --q-primary: #2563EB;
            --q-secondary: #94A3B8;
            --q-positive: #10B981;
            --q-negative: #F43F5E;
        }
        body { background: var(--color-bg-base); color: var(--color-text-main); }
        .text-positive { color: var(--color-positive) !important; }
        .text-negative { color: var(--color-negative) !important; }
        .text-primary { color: var(--color-primary) !important; }
        .text-main { color: var(--color-text-main) !important; }
        .text-muted { color: var(--color-text-muted) !important; }
        .text-green-700 { color: var(--color-positive) !important; }
        .text-red-700 { color: var(--color-negative) !important; }
        .text-blue-700 { color: var(--color-primary) !important; }
        .text-gray-500,
        .text-gray-600,
        .text-gray-700 { color: var(--color-text-muted) !important; }
        .text-gray-900 { color: var(--color-text-main) !important; }
        .app-shell { max-width: 1440px; margin: 0 auto; padding: 20px 24px 48px; gap: 16px; }
        .app-pill-nav {
            align-self: center;
            display: inline-flex;
            width: auto;
            max-width: 100%;
            align-items: center;
            gap: 8px;
            padding: 8px;
            border-radius: 999px;
            background: #FFFFFF;
            box-shadow: 0 10px 28px rgba(15, 23, 42, 0.13);
            overflow-x: auto;
        }
        .app-pill-nav-item {
            align-items: center;
            justify-content: center;
            min-width: 92px;
            border-radius: 999px;
            cursor: pointer;
            gap: 0;
            user-select: none;
            transition: background-color 300ms ease, color 300ms ease, padding 300ms ease, transform 300ms ease;
        }
        .app-pill-nav-item:hover {
            background: var(--color-interactive);
        }
        .app-pill-nav-item-active {
            padding: 8px 24px;
            background: var(--color-interactive);
            color: var(--color-primary);
        }
        .app-pill-nav-item-inactive {
            padding: 8px 12px;
            color: var(--color-text-muted);
        }
        .app-pill-nav-icon {
            font-size: 25px;
            line-height: 1;
            color: currentColor;
        }
        .app-pill-nav-label {
            margin-top: 2px;
            font-size: 12px;
            font-weight: 700;
            line-height: 1.16;
            color: currentColor;
            white-space: nowrap;
        }
        .app-section-viewport {
            position: relative;
            overflow-x: hidden;
            align-self: stretch;
        }
        .app-section-frame {
            min-width: 0;
            transform: translateX(0);
            will-change: transform, opacity;
        }
        .app-section-enter-from-right {
            animation: app-section-enter-from-right 280ms cubic-bezier(0.22, 0.61, 0.36, 1) both;
        }
        .app-section-enter-from-left {
            animation: app-section-enter-from-left 280ms cubic-bezier(0.22, 0.61, 0.36, 1) both;
        }
        @keyframes app-section-enter-from-right {
            from { opacity: 0.15; transform: translateX(48px); }
            to { opacity: 1; transform: translateX(0); }
        }
        @keyframes app-section-enter-from-left {
            from { opacity: 0.15; transform: translateX(-48px); }
            to { opacity: 1; transform: translateX(0); }
        }
        .page-title { font-size: 28px; font-weight: 750; margin-bottom: 16px; }
        .section-title { font-size: 18px; font-weight: 700; margin: 16px 0 8px; }
        .metric-card {
            position: relative;
            overflow: hidden;
            min-width: 220px;
            flex: 1;
            border-radius: 16px;
            background: var(--color-bg-surface);
            border: 1px solid #DBEAFE;
            box-shadow: 0 8px 22px rgba(15, 23, 42, 0.07);
        }
        .metric-label { font-size: 13px; color: var(--color-text-muted); }
        .metric-value { font-size: 24px; font-weight: 760; }
        .metric-card-icon {
            position: absolute;
            top: 14px;
            right: 16px;
            font-size: 28px;
            opacity: 0.22;
        }
        .investment-summary-card {
            position: relative;
            overflow: hidden;
            border: 1px solid rgba(226, 232, 240, 0.9);
        }
        .investment-summary-icon {
            position: absolute;
            top: 14px;
            right: 16px;
            font-size: 30px;
            color: var(--color-secondary);
            opacity: 0.34;
        }
        .investment-summary-balance-positive {
            background: var(--color-positive-bg);
            border-color: rgba(16, 185, 129, 0.28);
        }
        .investment-summary-balance-negative {
            background: var(--color-negative-bg);
            border-color: rgba(244, 63, 94, 0.28);
        }
        .chart-card {
            flex: 1;
            min-width: 420px;
            border-radius: 16px;
            background: var(--color-bg-surface);
            border: 1px solid #E0ECFF;
            box-shadow: 0 8px 22px rgba(15, 23, 42, 0.06);
        }
        .analysis-chart-card {
            width: 100%;
            min-width: 0;
            overflow: hidden;
        }
        .analysis-top-card {
            height: 400px;
            max-height: 400px;
        }
        .analysis-plotly {
            width: 100%;
            min-width: 0;
            max-width: 100%;
        }
        .plotly-chart { width: 100%; height: 420px; min-height: 420px; }
        .plotly-chart-tall { width: 100%; height: 520px; min-height: 520px; }
        .form-card, .table-card {
            width: 100%;
            border-radius: 16px;
            background: var(--color-bg-surface);
            border: 1px solid #E0ECFF;
            box-shadow: 0 8px 22px rgba(15, 23, 42, 0.05);
        }
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
        .investment-ops-table { grid-template-columns: 112px 96px minmax(220px, 1fr) 112px 112px 112px 96px; min-width: 960px; }
        .sector-table > *:nth-child(2),
        .sector-table > *:nth-child(3),
        .sector-table > *:nth-child(4),
        .transactions-table > *:nth-child(6),
        .investments-table > *:nth-child(3),
        .investments-table > *:nth-child(4),
        .investments-table > *:nth-child(5),
        .investments-table > *:nth-child(6),
        .investment-ops-table > *:nth-child(4),
        .investment-ops-table > *:nth-child(5),
        .investment-ops-table > *:nth-child(6) {
            text-align: right;
            font-variant-numeric: tabular-nums;
        }
        .movements-scroll {
            width: 100%;
            min-width: 1120px;
            max-height: 560px;
            overflow-y: auto;
            overflow-x: hidden;
            overscroll-behavior: contain;
        }
        .movement-loading-label {
            padding: 8px 6px 2px;
        }
        .current-assets-scroll {
            height: 420px;
            min-height: 420px;
            overflow-y: auto;
            overflow-x: hidden;
            width: 100%;
        }
        .current-assets-table {
            display: grid;
            grid-template-columns: minmax(0, 1.4fr) 104px 124px minmax(0, 1fr) 48px;
            width: 100%;
            min-width: 0;
            align-items: center;
            column-gap: 10px;
        }
        .current-assets-table > *:not(.current-assets-row) {
            min-width: 0;
            padding: 9px 6px;
            border-bottom: 1px solid #E2E8F0;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }
        .current-assets-table-header {
            color: var(--color-text-muted);
            font-weight: 700;
            position: sticky;
            top: 0;
            z-index: 1;
            background: var(--color-bg-surface);
        }
        .current-assets-row {
            grid-column: 1 / -1;
            display: grid;
            grid-template-columns: minmax(0, 1.4fr) 104px 124px minmax(0, 1fr) 48px;
            align-items: center;
            min-width: 0;
            min-height: 44px;
            border-bottom: 1px solid #E2E8F0;
            border-radius: 6px;
            transition: background-color 120ms ease, box-shadow 120ms ease;
        }
        .current-assets-row:hover {
            background: var(--color-interactive);
            box-shadow: inset 3px 0 0 #DBEAFE;
        }
        .current-assets-row > * {
            min-width: 0;
            padding: 9px 6px;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }
        .current-assets-name {
            font-weight: 650;
        }
        .current-assets-number {
            text-align: right;
            font-variant-numeric: tabular-nums;
        }
        .current-assets-badge {
            justify-self: start;
            max-width: 100%;
            padding: 4px 9px !important;
            border-radius: 999px;
            background: var(--color-interactive);
            color: var(--color-text-main);
            border: 1px solid #DBEAFE;
            font-size: 12px;
            font-weight: 700;
            line-height: 1.2;
        }
        .current-assets-action {
            display: flex;
            justify-content: flex-end;
            padding-right: 2px !important;
        }
        .table-header > *, .table-row > * { width: 100%; min-width: 0; }
        .table-header { color: var(--color-text-muted); border-bottom: 1px solid #E2E8F0; }
        .table-row { border-bottom: 1px solid #E2E8F0; min-height: 44px; }
        .date-group { margin-top: 16px; padding: 8px 12px; border-left: 4px solid var(--color-primary); background: var(--color-interactive); font-weight: 750; width: 100%; }
        .signed-amount-input.amount-positive .q-field__native,
        .signed-amount-input.amount-positive .q-field__label {
            color: var(--color-positive) !important;
            font-weight: 750;
        }
        .signed-amount-input.amount-negative .q-field__native,
        .signed-amount-input.amount-negative .q-field__label {
            color: var(--color-negative) !important;
            font-weight: 750;
        }
        .dialog-card { min-width: 520px; max-width: calc(100vw - 48px); gap: 14px; border-radius: 16px; }
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
        .asset-detail-dialog {
            width: min(1500px, calc(100vw - 32px)) !important;
            max-width: calc(100vw - 32px) !important;
            height: min(900px, calc(100vh - 32px)) !important;
            max-height: calc(100vh - 32px) !important;
            overflow: hidden;
            overflow-x: hidden;
            display: flex;
            flex-direction: column;
        }
        .asset-detail-body {
            flex: 1 1 auto;
            min-height: 0;
            width: 100%;
            overflow-y: auto;
            overflow-x: hidden;
            padding-right: 4px;
        }
        .asset-detail-metrics {
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 10px;
            width: 100%;
        }
        .asset-detail-metric {
            min-width: 0;
            padding: 10px 12px;
            border: 1px solid #E2E8F0;
            border-radius: 14px;
            background: var(--color-bg-base);
        }
        .asset-detail-metric-label {
            font-size: 12px;
            color: var(--color-text-muted);
            font-weight: 650;
        }
        .asset-detail-metric-value {
            margin-top: 3px;
            font-size: 18px;
            font-weight: 760;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }
        .asset-detail-top {
            display: grid;
            grid-template-columns: minmax(0, 1fr) 280px;
            gap: 16px;
            width: 100%;
            align-items: stretch;
        }
        .asset-detail-chart-panel,
        .asset-detail-values-panel {
            min-width: 0;
        }
        .asset-chart-tabs {
            min-height: 38px;
            box-shadow: none;
        }
        .asset-chart-tabs .q-tabs__content {
            gap: 4px;
        }
        .asset-chart-tabs .q-tab {
            min-height: 30px;
            padding: 0 14px;
            border-radius: 9999px;
            color: #64748B;
            font-weight: 700;
        }
        .asset-chart-tabs .q-tab--active {
            background: #FFFFFF;
            color: #1E293B;
            box-shadow: 0 1px 2px rgba(15, 23, 42, 0.08);
        }
        .asset-chart-panels,
        .asset-chart-tab-panel {
            background: transparent;
            padding: 0;
            box-shadow: none;
        }
        .asset-detail-plot {
            height: 500px;
            min-height: 500px;
        }
        .asset-detail-values-panel {
            display: flex;
            flex-direction: column;
            height: 500px;
            min-height: 500px;
        }
        .asset-detail-values-scroll {
            flex: 1 1 auto;
            min-height: 0;
            overflow-y: auto;
            overflow-x: hidden;
            border: 1px solid #E2E8F0;
            border-radius: 14px;
        }
        .asset-detail-values-table {
            display: grid;
            grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) minmax(0, 1fr);
            width: 100%;
            align-items: center;
        }
        .asset-detail-operations-scroll {
            width: 100%;
            max-height: 260px;
            overflow-y: auto;
            overflow-x: auto;
            border: 1px solid #E2E8F0;
            border-radius: 14px;
        }
        .asset-detail-operations-table {
            display: grid;
            grid-template-columns: 112px 96px 112px 112px 128px 128px 56px;
            min-width: 744px;
            width: 100%;
            align-items: center;
        }
        .asset-detail-values-table > *,
        .asset-detail-operations-table > * {
            min-width: 0;
            padding: 9px 8px;
            border-bottom: 1px solid #E2E8F0;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }
        .asset-detail-values-table > *:nth-child(3n + 2),
        .asset-detail-values-table > *:nth-child(3n + 3),
        .asset-detail-operations-table > *:nth-child(7n + 3),
        .asset-detail-operations-table > *:nth-child(7n + 4),
        .asset-detail-operations-table > *:nth-child(7n + 5),
        .asset-detail-operations-table > *:nth-child(7n + 6) {
            text-align: right;
            font-variant-numeric: tabular-nums;
        }
        .asset-detail-table-header {
            color: var(--color-text-muted);
            font-weight: 700;
            position: sticky;
            top: 0;
            z-index: 1;
            background: var(--color-bg-surface);
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
        .investment-entry-row > .investment-entry-cell:nth-child(5),
        .investment-entry-row > .investment-entry-cell:nth-child(6),
        .investment-entry-row > .investment-entry-cell:nth-child(7) {
            text-align: right;
            font-variant-numeric: tabular-nums;
        }
        .investment-entry-row > .investment-entry-cell:nth-child(5) .q-field__native,
        .investment-entry-row > .investment-entry-cell:nth-child(6) .q-field__native,
        .investment-entry-row > .investment-entry-cell:nth-child(7) .q-field__native,
        .investment-entry-row > .investment-entry-cell:nth-child(5) .q-field__suffix,
        .investment-entry-row > .investment-entry-cell:nth-child(6) .q-field__suffix,
        .investment-entry-row > .investment-entry-cell:nth-child(7) .q-field__suffix {
            text-align: right;
            font-variant-numeric: tabular-nums;
        }
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
        .investment-entry-header { color: var(--color-text-muted); border-bottom: 1px solid #E2E8F0; font-weight: 700; }
        .investment-entry-data { border-bottom: 1px solid #E2E8F0; min-height: 64px; }
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
            border-bottom: 1px solid #E2E8F0;
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
        .setup-step { background: #F1F5F9; color: var(--color-text-muted); }
        .setup-step-active { background: var(--color-interactive); color: var(--color-primary); }
        .setup-step-card {
            width: 100%;
            border-radius: 14px;
            background: var(--color-bg-surface);
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
            border: 1px solid #DBEAFE;
            border-radius: 12px;
            background: var(--color-bg-base);
        }
        .setup-chip-text {
            min-width: 0;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
            font-weight: 650;
        }
        .setup-chip-remove { color: var(--color-negative); }
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
            border: 1px solid #DBEAFE;
            border-radius: 14px;
            background: var(--color-bg-base);
        }
        .analysis-sector-chip:has(.q-checkbox[aria-checked="true"]) {
            border-color: #BFDBFE;
            background: var(--color-interactive);
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
            color: var(--color-text-main);
        }
        .compact-table .q-table__container { box-shadow: none; }
        @media (prefers-reduced-motion: reduce) {
            .app-section-enter-from-right,
            .app-section-enter-from-left {
                animation: none;
            }
        }
        @media (max-width: 900px) {
            .asset-detail-metrics {
                grid-template-columns: repeat(2, minmax(0, 1fr));
            }
            .asset-detail-top {
                grid-template-columns: minmax(0, 1fr);
            }
            .asset-detail-values-panel {
                height: 280px;
                min-height: 280px;
            }
        }
        </style>
        """
    )
