"""
ui/app.py — Ventana principal: ensambla el layout y orquesta el estado.

Estructura (de fuera hacia dentro):

    ┌───────────────────────────────────────────────────────────┐
    │  body                                                      │
    │  ┌─────────┬──────────────────────────────┬────────────┐  │
    │  │ Sidebar │  MainTable (buscador+tabla)   │  Preview   │  │
    │  └─────────┴──────────────────────────────┴────────────┘  │
    ├───────────────────────────────────────────────────────────┤
    │  Toolbar (destino + acciones)                             │
    ├───────────────────────────────────────────────────────────┤
    │  StatusBar                                                │
    └───────────────────────────────────────────────────────────┘

App es el único que conoce el estado completo (sesiones, proyecto activo,
búsqueda, selección) y conecta los callbacks de cada componente. Toda la
lógica pesada (escanear, exportar) corre en hilos para no bloquear la UI.
"""
import sys
import threading
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox

import styles as S
from widgets import StatusBar
from core.utils import (
    find_claude_dir, format_ts, extract_icon, open_path,
    create_desktop_shortcut, get_base_path,
)
from core.sessions import gather_all_sessions, group_by_project
from core.exporter import export_session, session_to_markdown, has_readable_turns
from ui.sidebar import Sidebar
from ui.main_table import MainTable
from ui.preview_panel import PreviewPanel
from ui.toolbar import Toolbar

DEFAULT_OUT_DIR = Path(r"D:\Claude Code sessions")


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Claude Code Session Exporter")
        self.configure(bg=S.BG_DEEP)
        self.minsize(1040, 620)
        self._center(1200, 740)

        S.init_ttk_styles(self)
        self._icon_path = extract_icon()
        self._apply_icon()

        # ── Estado ────────────────────────────────────────────────────────────
        self._all_sessions = []
        self._projects = []
        self._current_project = None     # None = "Todas las sesiones"
        self._search_query = ""
        self._selected = None
        self._sort_field = "last_ts"
        self._sort_rev = True

        self._build_ui()
        self._load_sessions()

        if sys.platform == "win32":
            self.after(800, self._maybe_offer_shortcut)

    # ── Ventana ───────────────────────────────────────────────────────────────
    def _center(self, w, h):
        self.update_idletasks()
        x = (self.winfo_screenwidth() - w) // 2
        y = (self.winfo_screenheight() - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")

    def _apply_icon(self):
        if not self._icon_path:
            return
        try:
            self.iconbitmap(default=str(self._icon_path))
        except Exception:
            try:
                self.iconbitmap(str(self._icon_path))
            except Exception:
                pass

    # ── Construcción del layout ───────────────────────────────────────────────
    def _build_ui(self):
        # Status bar (abajo del todo)
        self._status = StatusBar(self)
        self._status.pack(side="bottom", fill="x")
        tk.Frame(self, bg=S.BORDER, height=1).pack(side="bottom", fill="x")

        # Toolbar inferior
        self._toolbar = Toolbar(
            self, out_dir=DEFAULT_OUT_DIR,
            on_change_dir=self._pick_dir, on_open_dir=self._open_export_dir,
            on_export=self._export_selected, on_export_all=self._export_all,
            on_shortcut=lambda: self._create_shortcut(silent=False),
        )
        self._toolbar.pack(side="bottom", fill="x")
        tk.Frame(self, bg=S.BORDER, height=1).pack(side="bottom", fill="x")

        # Cuerpo: sidebar | tabla | preview
        body = tk.Frame(self, bg=S.BG_DEEP)
        body.pack(side="top", fill="both", expand=True)

        self._sidebar = Sidebar(body, on_select=self._on_project_select,
                                on_reload=self._load_sessions)
        self._sidebar.pack(side="left", fill="y")
        tk.Frame(body, bg=S.BORDER, width=1).pack(side="left", fill="y")

        self._preview = PreviewPanel(body)
        self._preview.pack(side="right", fill="y")
        tk.Frame(body, bg=S.BORDER, width=1).pack(side="right", fill="y")

        self._table = MainTable(body, on_select=self._on_session_select,
                                on_activate=self._on_session_activate,
                                on_search=self._on_search, on_sort=self._on_sort)
        self._table.pack(side="left", fill="both", expand=True)
        self._table.set_sort_indicator(self._sort_field, self._sort_rev)

    # ── Carga de sesiones (en hilo) ───────────────────────────────────────────
    def _load_sessions(self):
        self._status.spin("Buscando sesiones de Claude Code…")
        self._toolbar.set_export_enabled(False)

        def worker():
            claude_dir = find_claude_dir()
            if not claude_dir:
                self.after(0, lambda: self._status.error(
                    "No se encontró ~/.claude — ¿Claude Code instalado?"))
                return
            projects = claude_dir / "projects"
            if not projects.exists():
                self.after(0, lambda: self._status.error(
                    f"Carpeta 'projects' no encontrada en {claude_dir}"))
                return
            try:
                sessions = gather_all_sessions(projects)
            except Exception as e:
                self.after(0, lambda: self._status.error(f"Error al leer sesiones: {e}"))
                return
            self.after(0, lambda: self._on_sessions_loaded(sessions))

        threading.Thread(target=worker, daemon=True).start()

    def _on_sessions_loaded(self, sessions):
        self._all_sessions = sessions
        self._projects = group_by_project(sessions)
        self._selected = None
        self._preview.show_placeholder()
        self._toolbar.set_export_enabled(False)

        self._sidebar.set_projects(self._projects, len(sessions))
        self._refresh_table()

        n, pj = len(sessions), len(self._projects)
        if n == 0:
            self._status.warn("No se encontraron sesiones guardadas")
        else:
            ses = "sesión" if n == 1 else "sesiones"
            vig = "vigente" if n == 1 else "vigentes"
            pjw = "proyecto" if pj == 1 else "proyectos"
            self._status.ok(f"{n} {ses} {vig} en {pj} {pjw}")

    # ── Filtrado / orden ──────────────────────────────────────────────────────
    def _base_scope(self):
        """Sesiones del ámbito actual (todas o las del proyecto seleccionado)."""
        if self._current_project is None:
            return self._all_sessions
        return self._current_project.sessions

    def _sorted(self, sessions):
        field = self._sort_field
        def key(s):
            if field == "message_count":
                return s.message_count
            if field == "display_name":
                return s.display_name.lower()
            if field == "project":
                return s.project.lower()
            return s.last_ts or ""
        return sorted(sessions, key=key, reverse=self._sort_rev)

    def _refresh_table(self):
        base = self._base_scope()
        q = self._search_query
        if q:
            visible = [s for s in base if self._matches(s, q)]
        else:
            visible = list(base)
        visible = self._sorted(visible)
        self._table.set_sessions(visible, subtitle_total=len(base))

    @staticmethod
    def _matches(s, q):
        return (q in s.project.lower()
                or q in (s.project_full or "").lower()
                or q in s.display_name.lower()
                or q in (s.first_user_msg or "").lower()
                or q in format_ts(s.last_ts).lower())

    # ── Callbacks de UI ───────────────────────────────────────────────────────
    def _on_project_select(self, project):
        self._current_project = project
        self._refresh_table()
        name = project.name if project else "todas las sesiones"
        self._status.info(f"Mostrando {name}")

    def _on_search(self, query):
        self._search_query = (query or "").lower().strip()
        self._refresh_table()

    def _on_sort(self, field):
        if self._sort_field == field:
            self._sort_rev = not self._sort_rev
        else:
            self._sort_field = field
            self._sort_rev = (field in ("last_ts", "message_count"))
        self._table.set_sort_indicator(self._sort_field, self._sort_rev)
        self._refresh_table()

    def _on_session_select(self, session):
        self._selected = session
        self._toolbar.set_export_enabled(True)
        self._preview.show_session(session)

    def _on_session_activate(self, session):
        self._selected = session
        self._toolbar.set_export_enabled(True)
        self._export_selected()

    # ── Acciones: destino ─────────────────────────────────────────────────────
    def _pick_dir(self):
        chosen = filedialog.askdirectory(
            title="Selecciona la carpeta de destino",
            initialdir=self._toolbar.out_dir)
        if chosen:
            self._toolbar.out_dir = chosen

    def _open_export_dir(self):
        d = Path(self._toolbar.out_dir)
        try:
            d.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        open_path(d)

    # ── Acciones: exportar ────────────────────────────────────────────────────
    def _export_selected(self):
        session = self._selected
        if not session:
            self._status.warn("Selecciona una sesión primero")
            return
        out_dir = Path(self._toolbar.out_dir)
        try:
            out_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            self._status.error(f"No se puede crear la carpeta: {e}")
            return

        self._status.spin("Exportando…")
        self._toolbar.set_export_enabled(False)

        def worker():
            try:
                md = session_to_markdown(session)
                out_path = export_session(session, out_dir)
                self.after(0, lambda: self._on_exported(out_path, md))
            except Exception as e:
                self.after(0, lambda: self._status.error(f"Error al exportar: {e}"))
                self.after(0, lambda: self._toolbar.set_export_enabled(True))

        threading.Thread(target=worker, daemon=True).start()

    def _on_exported(self, out_path, content):
        self._toolbar.set_export_enabled(True)
        size_kb = len(content.encode("utf-8")) / 1024
        if has_readable_turns(content):
            self._status.ok(f"Exportado → {out_path.name}  ({size_kb:.1f} KB)")
        else:
            self._status.warn(f"Sesión sin contenido legible → {out_path.name}")

    def _export_all(self):
        base = self._base_scope()
        q = self._search_query
        targets = [s for s in base if self._matches(s, q)] if q else list(base)
        if not targets:
            self._status.warn("No hay sesiones para exportar")
            return

        out_dir = Path(self._toolbar.out_dir)
        scope = self._current_project.name if self._current_project else "todas las sesiones"
        if not messagebox.askyesno(
            "Exportar todo",
            f"¿Exportar {len(targets)} sesión(es) de «{scope}»\n"
            f"a:\n{out_dir}?",
            icon="question"):
            return

        try:
            out_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            self._status.error(f"No se puede crear la carpeta: {e}")
            return

        self._status.spin(f"Exportando {len(targets)} sesiones…")
        self._toolbar.set_export_enabled(False)

        def worker():
            ok, fail = 0, 0
            for s in targets:
                try:
                    export_session(s, out_dir)
                    ok += 1
                except Exception:
                    fail += 1
            self.after(0, lambda: self._on_export_all_done(ok, fail))

        threading.Thread(target=worker, daemon=True).start()

    def _on_export_all_done(self, ok, fail):
        self._toolbar.set_export_enabled(self._selected is not None)
        if fail:
            self._status.warn(f"Exportadas {ok}, fallaron {fail}")
        else:
            self._status.ok(f"Exportadas {ok} sesiones a la carpeta de destino")

    # ── Acceso directo ────────────────────────────────────────────────────────
    def _maybe_offer_shortcut(self):
        flag = Path.home() / ".claude_exporter_shortcut_created"
        if flag.exists():
            return
        if messagebox.askyesno(
            "Acceso directo",
            "¿Quieres crear un acceso directo en el Escritorio\n"
            "para abrir esta aplicación con un solo clic?",
            icon="question"):
            self._create_shortcut(silent=False)
            try:
                flag.touch()
            except Exception:
                pass

    def _create_shortcut(self, silent=True):
        if sys.platform != "win32":
            self._status.warn("Acceso directo solo disponible en Windows")
            return
        entry = get_base_path() / "main.py"
        result = create_desktop_shortcut(entry, self._icon_path)
        if result:
            self._status.ok("Acceso directo creado en el Escritorio")
            if not silent:
                messagebox.showinfo(
                    "Acceso directo creado",
                    f"✔  Acceso directo creado:\n{result}\n\n"
                    "Desde ahora puedes abrirlo desde el Escritorio.")
        else:
            self._status.error("No se pudo crear el acceso directo")
            if not silent:
                messagebox.showerror(
                    "Error",
                    "No se pudo crear el acceso directo.\n"
                    "Asegúrate de que PowerShell esté disponible.")
