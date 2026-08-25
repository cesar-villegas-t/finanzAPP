import nicegui.run
from fastapi.responses import Response
from nicegui import app, ui
from nicegui.storage import Storage
from pathlib import Path

from config import NICEGUI_STORAGE_DIR, ensure_private_dirs, get_storage_secret
from db.connection import create_user, init_db, list_users, verify_user
from db.queries import configurar_catalogos_iniciales
from ui.components import quasar_dark_props
from ui.styles import add_styles
from ui.views.analysis import render_analisis_gasto
from ui.views.dashboard import render_saldo_global
from ui.views.investments import open_preferences_drawer, render_inversiones
from ui.views.transactions import render_ingresos_gastos


# The managed Windows workspace can block multiprocessing pipes during NiceGUI startup.
# This app does not use ui.run.cpu_bound, so the process pool can be disabled safely.
nicegui.run.setup = lambda: None

ensure_private_dirs()
STORAGE_SECRET = get_storage_secret()
Storage.secret = STORAGE_SECRET
Storage.path = NICEGUI_STORAGE_DIR
app.add_static_files("/static", Path(__file__).parent / "static")
FAVICON_PATH = Path(__file__).parent / "static" / "icons" / "favicon.svg"

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
        "background_color": "#F8FAFC",
        "theme_color": "#2563EB",
        "icons": [
            {
                "src": "/static/icons/favicon.svg",
                "sizes": "any",
                "type": "image/svg+xml",
                "purpose": "any",
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
        clear_user_storage()
        return False
    username = app.storage.user.get("username")
    if not username:
        return False
    if username not in list_users():
        clear_user_storage()
        return False
    return True


def clear_user_storage():
    try:
        app.storage.user.clear()
    except PermissionError:
        # Windows can keep the persisted NiceGUI storage file locked when
        # another dev-server process is still running. The in-memory dict is
        # already cleared before NiceGUI unlinks the file.
        pass


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

                new_item_input = ui.input(f"Añadir {step['label'].lower()}").props(
                    quasar_dark_props("outlined dense")
                ).classes("w-full dark:bg-slate-900 dark:text-slate-100 dark:border-slate-700")

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

def render_auth_card(on_login_callback, on_register_callback, initial_mode="login"):
    mode = {"value": initial_mode if initial_mode in {"login", "register"} else "login"}
    password_visible = {"value": False}

    with ui.element("div").classes(
        "min-h-screen w-full bg-slate-50 dark:bg-slate-900 flex items-center justify-center p-6"
    ):
        with ui.card().classes(
            "w-full max-w-sm bg-white dark:bg-slate-800 p-8 rounded-2xl "
            "shadow-2xl shadow-slate-200/60 dark:shadow-black/30 gap-6"
        ):
            with ui.column().classes("w-full items-center gap-2 text-center"):
                ui.image("/static/icons/favicon.svg").classes("w-12 h-12")
                with ui.row().classes("items-baseline justify-center gap-0"):
                    ui.label("Finanz").classes("text-3xl font-bold text-slate-900 dark:text-slate-100")
                    ui.label("APP").classes("text-3xl font-bold text-[#2563EB]")
                ui.label("Gestión patrimonial inteligente").classes("text-sm text-slate-400")

            @ui.refreshable
            def render_auth_form():
                user_input = None
                password_input = None
                confirm_input = None

                def set_mode(new_mode):
                    mode["value"] = new_mode
                    password_visible["value"] = False
                    render_auth_form.refresh()

                def submit():
                    username = (user_input.value or "").strip()
                    password = password_input.value or ""
                    confirm_password = confirm_input.value if confirm_input else None

                    if not username or not password or (mode["value"] == "register" and not confirm_password):
                        ui.notify("Completa todos los campos.", color="warning")
                        return
                    if mode["value"] == "register" and password != confirm_password:
                        ui.notify("Las contraseñas no coinciden.", color="warning")
                        return

                    if mode["value"] == "login":
                        on_login_callback(username, password)
                    else:
                        on_register_callback(username, password)

                def toggle_password_visibility():
                    password_visible["value"] = not password_visible["value"]
                    password_input.props(f'type={"text" if password_visible["value"] else "password"}')
                    password_visibility_icon.props(
                        f'name={"visibility" if password_visible["value"] else "visibility_off"}'
                    )

                with ui.tabs(value=mode["value"]).classes(
                    "asset-chart-tabs auth-mode-tabs bg-[#F8FAFC] dark:bg-slate-900 rounded-full p-1 w-full"
                ).props('dense no-caps active-color="dark" indicator-color="transparent"') as auth_tabs:
                    ui.tab("login", label="Iniciar sesión")
                    ui.tab("register", label="Crear usuario")
                auth_tabs.on("update:model-value", lambda event: set_mode(event.args))

                with ui.column().classes("w-full gap-4"):
                    user_input = ui.input("Usuario").props(
                        quasar_dark_props('outlined color=blue-8 input-class="text-lg"')
                    ).classes("w-full rounded-xl dark:bg-slate-900 dark:text-slate-100 dark:border-slate-700")
                    with user_input.add_slot("prepend"):
                        ui.icon("person").classes("text-slate-400")

                    password_input = ui.input("Contraseña", password=not password_visible["value"]).props(
                        quasar_dark_props('outlined color=blue-8 input-class="text-lg"')
                    ).classes("w-full rounded-xl dark:bg-slate-900 dark:text-slate-100 dark:border-slate-700")
                    with password_input.add_slot("prepend"):
                        ui.icon("lock").classes("text-slate-400")
                    with password_input.add_slot("append"):
                        password_visibility_icon = ui.icon(
                            "visibility" if password_visible["value"] else "visibility_off"
                        ).classes("cursor-pointer text-slate-400 hover:text-[#2563EB] transition-colors")
                    password_visibility_icon.on("click", lambda _: toggle_password_visibility())

                    if mode["value"] == "register":
                        confirm_input = ui.input("Confirmar Contraseña", password=True).props(
                            quasar_dark_props('outlined color=blue-8 input-class="text-lg"')
                        ).classes("w-full rounded-xl dark:bg-slate-900 dark:text-slate-100 dark:border-slate-700")
                        with confirm_input.add_slot("prepend"):
                            ui.icon("lock_reset").classes("text-slate-400")

                    inputs = [user_input, password_input]
                    if confirm_input:
                        inputs.append(confirm_input)
                    for input_field in inputs:
                        input_field.on("keydown.enter", lambda _: submit())

                    button_label = "Acceder" if mode["value"] == "login" else "Crear Cuenta"
                    ui.button(button_label, on_click=submit).props("unelevated no-caps").classes(
                        "w-full bg-[#2563EB] text-white rounded-xl py-3 font-semibold text-base transition-colors hover:bg-blue-700"
                    )

            render_auth_form()


def handle_login(username, password):
    username_valido = verify_user(username, password)
    if not username_valido:
        ui.notify("Usuario o contraseña incorrectos.", color="negative")
        return
    app.storage.user.update({
        "authenticated": True,
        "username": username_valido,
    })
    ui.navigate.to("/")


def handle_register(username, password):
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


@ui.page("/login")
def login():
    add_styles()
    ui.dark_mode(value=bool(app.storage.user.get("dark_mode", False)))
    if sesion_autenticada():
        ui.navigate.to("/")
        return
    render_auth_card(handle_login, handle_register)


@ui.page("/register")
def register():
    add_styles()
    ui.dark_mode(value=bool(app.storage.user.get("dark_mode", False)))
    if sesion_autenticada():
        ui.navigate.to("/")
        return
    render_auth_card(handle_login, handle_register, initial_mode="register")


def logout():
    clear_user_storage()
    ui.navigate.to("/login")


@ui.page("/")
def main(tab: str = "saldo"):
    add_styles()
    dark = ui.dark_mode(value=bool(app.storage.user.get("dark_mode", False)))
    if not sesion_autenticada():
        ui.navigate.to("/login")
        return

    username = username_actual()
    user_initial = (username[:1] or "?").upper()

    def toggle_dark_mode(value=None):
        target_value = not bool(dark.value) if value is None else bool(value)
        if target_value != bool(dark.value):
            dark.toggle()
        app.storage.user["dark_mode"] = bool(dark.value)
        if content is not None:
            render_active_tab(active_tab["value"])

    with ui.column().classes(
        "app-shell w-full min-h-screen bg-slate-50 dark:bg-slate-900 "
        "text-slate-900 dark:text-slate-100 transition-colors duration-300"
    ):
        with ui.row().classes("items-center justify-between w-full"):
            with ui.row().classes("items-center gap-2"):
                ui.html("""
                    <svg width="32" height="32" viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
                      <g transform="skewX(-12) translate(8, 0)">
                        <rect x="2" y="4" width="6" height="24" rx="1.5" fill="currentColor"/>
                        <rect x="10" y="4" width="16" height="6" rx="1.5" fill="#2563EB"/>
                        <rect x="10" y="14" width="10" height="6" rx="1.5" fill="#10B981"/>
                      </g>
                    </svg>
                """).classes("text-slate-900 dark:text-slate-100")
                with ui.row().classes("gap-0 items-baseline text-xl"):
                    ui.label("Finanz").classes("font-bold text-slate-900 dark:text-slate-100")
                    ui.label("APP").classes("font-medium text-[#2563EB]")
            with ui.row().classes("items-center gap-2"):
                with ui.button(user_initial).props("round unelevated").style(
                    "background-color: #EFF6FF; color: #2563EB;"
                ):
                    with ui.menu().classes("rounded-2xl p-2 min-w-[210px] bg-white dark:bg-slate-800") as user_menu:
                        ui.label(username).classes(
                            "px-3 pt-2 pb-1 text-sm font-bold text-slate-900 dark:text-slate-100"
                        )
                        ui.separator().classes("my-1 bg-[#E2E8F0] dark:bg-slate-700")

                        def open_preferences_from_menu():
                            user_menu.close()
                            with ui.context.client.content:
                                open_preferences_drawer(
                                    username,
                                    is_dark=lambda: bool(dark.value),
                                    on_toggle_theme=toggle_dark_mode,
                                )

                        with ui.item(on_click=open_preferences_from_menu).classes(
                            "rounded-xl px-3 py-2 text-slate-500 dark:text-slate-400"
                        ):
                            with ui.item_section().props("avatar"):
                                ui.icon("settings").classes("text-slate-500 dark:text-slate-400")
                            with ui.item_section():
                                ui.label("Preferencias").classes(
                                    "text-sm font-medium text-slate-500 dark:text-slate-400"
                                )

                        with ui.item(on_click=logout).classes("rounded-xl px-3 py-2 text-[#F43F5E]"):
                            with ui.item_section().props("avatar"):
                                ui.icon("logout").classes("text-[#F43F5E]")
                            with ui.item_section():
                                ui.label("Cerrar sesión").classes("text-sm font-medium text-[#F43F5E]")

        nav_items = [
            ("saldo", "Saldo Global", "account_balance"),
            ("movimientos", "Ingresos y Gastos", "receipt_long"),
            ("analisis", "Análisis de Gasto", "insert_chart"),
            ("inversiones", "Inversiones", "trending_up"),
        ]
        tab_order = {key: index for index, (key, _, _) in enumerate(nav_items)}

        content = None
        renderers = {}
        active_tab = {"value": tab if tab in tab_order else "inversiones"}

        def render_active_tab(tab_name, *, animate=False):
            previous_tab = active_tab["value"]
            active_tab["value"] = tab_name if tab_name in renderers else "saldo"
            direction_class = ""
            if animate and previous_tab != active_tab["value"]:
                if tab_order[active_tab["value"]] > tab_order[previous_tab]:
                    direction_class = "app-section-enter-from-right"
                else:
                    direction_class = "app-section-enter-from-left"
            content.clear()
            with content:
                with ui.column().classes(f"app-section-frame {direction_class} w-full"):
                    renderers.get(active_tab["value"], renderers["saldo"])()

        @ui.refreshable
        def render_navigation():
            with ui.row().classes("app-pill-nav rounded-full bg-white dark:bg-slate-800 shadow-lg"):
                for key, label, icon in nav_items:
                    is_active = active_tab["value"] == key
                    item_classes = (
                        "app-pill-nav-item app-pill-nav-item-active items-center justify-center rounded-full transition-all duration-300"
                        if is_active
                        else "app-pill-nav-item app-pill-nav-item-inactive items-center justify-center rounded-full transition-all duration-300"
                    )

                    def select_tab(tab_name=key):
                        if tab_name == active_tab["value"]:
                            return
                        render_active_tab(tab_name, animate=True)
                        render_navigation.refresh()

                    with ui.column().classes(item_classes).on("click", select_tab):
                        ui.icon(icon).classes("app-pill-nav-icon")
                        ui.label(label).classes("app-pill-nav-label")

        renderers.update({
            "saldo": lambda: render_saldo_global(username, is_dark=bool(dark.value)),
            "movimientos": lambda: render_ingresos_gastos(
                lambda: render_active_tab("movimientos"),
                username,
                is_dark=bool(dark.value),
            ),
            "analisis": lambda: render_analisis_gasto(username, is_dark=bool(dark.value)),
            "inversiones": lambda: render_inversiones(
                lambda: render_active_tab("inversiones"),
                username,
                is_dark=bool(dark.value),
            ),
        })

        render_navigation()
        content = ui.column().classes("app-section-viewport w-full")
        render_active_tab(active_tab["value"])
        if app.storage.user.get("needs_initial_setup"):
            ui.timer(0.2, lambda: open_initial_setup_dialog(lambda: None), once=True)


if __name__ == "__main__":
    init_db()
    ui.run(
        title="FinanzAPP",
        favicon=FAVICON_PATH,
        host="127.0.0.1",
        port=8008,
        reload=False,
        storage_secret=STORAGE_SECRET,
    )
