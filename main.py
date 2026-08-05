import nicegui.run
from fastapi.responses import Response
from nicegui import app, ui
from nicegui.storage import Storage
from pathlib import Path

from config import NICEGUI_STORAGE_DIR, ensure_private_dirs, get_storage_secret
from db.connection import create_user, init_db, list_users, verify_user
from db.queries import configurar_catalogos_iniciales
from ui.styles import add_styles
from ui.views.analysis import render_analisis_gasto
from ui.views.dashboard import render_saldo_global
from ui.views.investments import render_inversiones
from ui.views.transactions import render_ingresos_gastos


# The managed Windows workspace can block multiprocessing pipes during NiceGUI startup.
# This app does not use ui.run.cpu_bound, so the process pool can be disabled safely.
nicegui.run.setup = lambda: None

ensure_private_dirs()
STORAGE_SECRET = get_storage_secret()
Storage.secret = STORAGE_SECRET
Storage.path = NICEGUI_STORAGE_DIR
app.add_static_files("/static", Path(__file__).parent / "static")

DEFAULT_SETUP_CUENTAS = ["BBVA", "Santander", "Revolut", "Efectivo"]
DEFAULT_SETUP_SECTORES = ["Balance inicial", "Sueldo", "Restaurantes", "Compras", "Transporte", "Otros"]
DEFAULT_SETUP_BROKERS = ["MyInvestor", "Trade Republic", "XTB"]


@app.get("/manifest.json", include_in_schema=False)
def manifest():
    return {
        "name": "FinanzAPP",
        "short_name": "Finanzas",
        "description": "Aplicación personal para gestionar finanzas, gastos e inversiones.",
        "start_url": "/",
        "scope": "/",
        "display": "standalone",
        "orientation": "portrait",
        "background_color": "#f6f7fb",
        "theme_color": "#2563eb",
        "icons": [
            {
                "src": "/static/icons/icon-192.png",
                "sizes": "192x192",
                "type": "image/png",
                "purpose": "any maskable",
            },
            {
                "src": "/static/icons/icon-512.png",
                "sizes": "512x512",
                "type": "image/png",
                "purpose": "any maskable",
            },
        ],
    }


@app.get("/service-worker.js", include_in_schema=False)
def service_worker():
    script = """
const CACHE_NAME = 'mis-finanzas-pwa-v1';
const APP_SHELL = ['/', '/manifest.json'];

self.addEventListener('install', event => {
  self.skipWaiting();
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => cache.addAll(APP_SHELL))
  );
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(key => key !== CACHE_NAME).map(key => caches.delete(key)))
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', event => {
  if (event.request.method !== 'GET') return;
  event.respondWith(
    fetch(event.request).catch(() => caches.match(event.request).then(response => response || caches.match('/')))
  );
});
"""
    return Response(
        content=script.strip(),
        media_type="application/javascript",
        headers={"Service-Worker-Allowed": "/"},
    )


def sesion_autenticada():
    if not app.storage.user.get("authenticated"):
        app.storage.user.clear()
        return False
    username = app.storage.user.get("username")
    if not username:
        return False
    if username not in list_users():
        app.storage.user.clear()
        return False
    return True


def username_actual():
    return app.storage.user.get("username")


def open_initial_setup_dialog(on_done):
    steps = [
        {
            "title": "Bancos",
            "description": "Indica los bancos o cuentas que quieres usar para clasificar movimientos.",
            "label": "Bancos o cuentas",
            "defaults": DEFAULT_SETUP_CUENTAS,
        },
        {
            "title": "Sectores",
            "description": "Define los sectores que usarás para agrupar gastos e ingresos.",
            "label": "Sectores",
            "defaults": DEFAULT_SETUP_SECTORES,
        },
        {
            "title": "Brokers",
            "description": "Indica los brokers que utilizarás para tus inversiones.",
            "label": "Brokers",
            "defaults": DEFAULT_SETUP_BROKERS,
        },
    ]
    values = [list(step["defaults"]) for step in steps]
    current_step = 0

    def clean_values(items):
        values_clean = []
        seen = set()
        for item in items:
            item = (item or "").strip()
            key = item.lower()
            if item and key not in seen:
                values_clean.append(item)
                seen.add(key)
        return values_clean

    def save_setup(use_defaults=False):
        cuentas = DEFAULT_SETUP_CUENTAS if use_defaults else clean_values(values[0])
        sectores = DEFAULT_SETUP_SECTORES if use_defaults else clean_values(values[1])
        brokers = DEFAULT_SETUP_BROKERS if use_defaults else clean_values(values[2])
        if not cuentas or not sectores or not brokers:
            ui.notify("Completa al menos un valor en bancos, sectores y brokers.", color="warning")
            return
        configurar_catalogos_iniciales(cuentas, sectores, brokers)
        app.storage.user["needs_initial_setup"] = False
        dialog.close()
        on_done()

    with ui.dialog() as dialog, ui.card().classes("dialog-card setup-dialog"):
        with ui.row().classes("w-full items-start justify-between"):
            with ui.column().classes("gap-1"):
                ui.label("Configuración inicial").classes("text-2xl font-semibold")
                ui.label("Personaliza los catálogos básicos de tu cuenta.").classes("text-sm text-gray-500")
            ui.button(
                "Configurar más adelante",
                on_click=lambda: save_setup(use_defaults=True),
            ).props("flat dense")

        @ui.refreshable
        def render_step():
            nonlocal current_step
            step = steps[current_step]
            with ui.row().classes("setup-progress w-full"):
                for index, item in enumerate(steps):
                    step_class = "setup-step-active" if index == current_step else "setup-step"
                    ui.label(f"{index + 1}. {item['title']}").classes(step_class)

            with ui.card().classes("setup-step-card"):
                ui.label(f"Paso {current_step + 1}: {step['title']}").classes("text-xl font-semibold")
                ui.label(step["description"]).classes("text-sm text-gray-600")

                with ui.element("div").classes("setup-chip-list"):
                    for index, item in enumerate(values[current_step]):
                        with ui.element("div").classes("setup-chip"):
                            ui.label(item).classes("setup-chip-text")

                            def remove_item(index=index):
                                values[current_step].pop(index)
                                render_step.refresh()

                            ui.button(icon="close", on_click=remove_item).props("flat dense round").classes("setup-chip-remove")

                new_item_input = ui.input(f"Añadir {step['label'].lower()}").classes("w-full")

                def add_item():
                    item = (new_item_input.value or "").strip()
                    if not item:
                        return
                    existing = {value.lower() for value in values[current_step]}
                    if item.lower() in existing:
                        ui.notify("Ese valor ya está en la lista.", color="warning")
                        return
                    values[current_step].append(item)
                    render_step.refresh()

                new_item_input.on("keydown.enter", lambda _: add_item())
                ui.button("Añadir", icon="add", on_click=add_item).props("outline")

            with ui.row().classes("w-full justify-end gap-2"):
                def go_back():
                    nonlocal current_step
                    current_step -= 1
                    render_step.refresh()

                def go_next():
                    nonlocal current_step
                    if not clean_values(values[current_step]):
                        ui.notify("Deja al menos un valor en este paso.", color="warning")
                        return
                    current_step += 1
                    render_step.refresh()

                def finish():
                    save_setup()

                if current_step > 0:
                    ui.button("Atrás", icon="arrow_back", on_click=go_back).props("outline")
                if current_step < len(steps) - 1:
                    ui.button("Siguiente", icon="arrow_forward", on_click=go_next)
                else:
                    ui.button("Guardar configuración", icon="save", on_click=finish)

        render_step()
    dialog.props("persistent")
    dialog.open()

@ui.page("/login")
def login():
    add_styles()
    if sesion_autenticada():
        ui.navigate.to("/")
        return

    with ui.column().classes("app-shell w-full items-center"):
        with ui.card().classes("dialog-card").style("margin-top: 12vh;"):
            ui.label("FinanzAPP").classes("text-3xl font-bold")
            ui.label("Inicia sesión para continuar").classes("text-sm text-gray-500")
            user_input = ui.input("Usuario").classes("w-full")
            password_input = ui.input(
                "Contraseña",
                password=True,
                password_toggle_button=True,
            ).classes("w-full")

            def do_login():
                username = (user_input.value or "").strip()
                password = password_input.value or ""
                username_valido = verify_user(username, password)
                if not username_valido:
                    ui.notify("Usuario o contraseña incorrectos.", color="negative")
                    return
                app.storage.user.update({
                    "authenticated": True,
                    "username": username_valido,
                })
                ui.navigate.to("/")

            password_input.on("keydown.enter", lambda _: do_login())
            ui.button("Entrar", icon="login", on_click=do_login).classes("w-full")
            ui.button("Crear usuario", icon="person_add", on_click=lambda: ui.navigate.to("/register")).props("outline").classes("w-full")


@ui.page("/register")
def register():
    add_styles()
    if sesion_autenticada():
        ui.navigate.to("/")
        return

    with ui.column().classes("app-shell w-full items-center"):
        with ui.card().classes("dialog-card").style("margin-top: 10vh;"):
            ui.label("Crear usuario").classes("text-3xl font-bold")
            ui.label("La contraseña debe tener mínimo 8 caracteres, una mayúscula y un número.").classes("text-sm text-gray-500")
            user_input = ui.input("Usuario").classes("w-full")
            password_input = ui.input(
                "Contraseña",
                password=True,
                password_toggle_button=True,
            ).classes("w-full")
            confirm_input = ui.input(
                "Confirmar contraseña",
                password=True,
                password_toggle_button=True,
            ).classes("w-full")

            def do_register():
                username = (user_input.value or "").strip()
                password = password_input.value or ""
                confirm_password = confirm_input.value or ""
                if password != confirm_password:
                    ui.notify("Las contraseñas no coinciden.", color="warning")
                    return
                try:
                    username_creado = create_user(username, password)
                except ValueError as exc:
                    ui.notify(str(exc), color="warning")
                    return
                app.storage.user.update({
                    "authenticated": True,
                    "username": username_creado,
                    "needs_initial_setup": True,
                })
                ui.navigate.to("/")

            confirm_input.on("keydown.enter", lambda _: do_register())
            ui.button("Crear cuenta", icon="person_add", on_click=do_register).classes("w-full")
            ui.button("Volver al login", icon="arrow_back", on_click=lambda: ui.navigate.to("/login")).props("outline").classes("w-full")


def logout():
    app.storage.user.clear()
    ui.navigate.to("/login")


@ui.page("/")
def main(tab: str = "saldo"):
    add_styles()
    if not sesion_autenticada():
        ui.navigate.to("/login")
        return

    username = username_actual()
    with ui.column().classes("app-shell w-full"):
        with ui.row().classes("items-center justify-between w-full"):
            ui.label("FinanzAPP").classes("text-3xl font-bold")
            with ui.row().classes("items-center gap-3"):
                ui.label(f"Usuario: {username}").classes("text-sm text-gray-500")
                ui.button("Cerrar sesión / cambiar usuario", icon="logout", on_click=logout).props("outline dense")

        with ui.tabs().classes("w-full") as tabs:
            ui.tab("saldo", label="Saldo Global", icon="account_balance")
            ui.tab("movimientos", label="Ingresos y Gastos", icon="receipt_long")
            ui.tab("analisis", label="Análisis de gasto", icon="analytics")
            ui.tab("inversiones", label="Inversiones", icon="trending_up")

        content = ui.column().classes("w-full")
        renderers = {}

        def render_active_tab(tab_name):
            content.clear()
            with content:
                renderers.get(tab_name, renderers["saldo"])()

        renderers.update({
            "saldo": lambda: render_saldo_global(username),
            "movimientos": lambda: render_ingresos_gastos(lambda: render_active_tab("movimientos"), username),
            "analisis": lambda: render_analisis_gasto(username),
            "inversiones": lambda: render_inversiones(lambda: render_active_tab("inversiones"), username),
        })

        initial_tab = tab if tab in renderers else "saldo"
        tabs.on_value_change(lambda e: render_active_tab(e.value))
        tabs.value = initial_tab
        render_active_tab(initial_tab)
        if app.storage.user.get("needs_initial_setup"):
            ui.timer(0.2, lambda: open_initial_setup_dialog(lambda: None), once=True)


if __name__ == "__main__":
    init_db()
    ui.run(
        title="FinanzAPP",
        host="127.0.0.1",
        port=8008,
        reload=False,
        storage_secret=STORAGE_SECRET,
    )

