"""
Claude Code Session Exporter — GUI v3
Interfaz gráfica para exportar sesiones de Claude Code a Markdown.
Ejecutar con: pythonw claude_exporter_gui-3.pyw  (sin consola en Windows)
"""

import json
import math
import os
import sys
import threading
import subprocess
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox


# ══════════════════════════════════════════════════════════════════════════════
#  PALETA DE COLORES
# ══════════════════════════════════════════════════════════════════════════════
BG          = "#0f1117"   # fondo principal
BG2         = "#1a1d27"   # paneles secundarios
BG3         = "#22263a"   # filas alternas / inputs
ACCENT      = "#7c5cfc"   # morado Claude
ACCENT2     = "#5b8dee"   # azul acento
SUCCESS     = "#3ecf8e"   # verde éxito
WARNING     = "#f6c344"   # amarillo advertencia
DANGER      = "#ff6b6b"   # rojo error
TEXT        = "#e8eaf0"   # texto principal
TEXT_DIM    = "#6b7280"   # texto secundario
BORDER      = "#2d3148"   # bordes

# Versiones RGB para interpolar gradientes
_ACCENT_RGB  = (124, 92, 252)
_ACCENT2_RGB = (91, 141, 238)
_BG_RGB      = (15, 17, 23)
_BG2_RGB     = (26, 29, 39)
_BG3_RGB     = (34, 38, 58)


# ══════════════════════════════════════════════════════════════════════════════
#  UTILIDADES GRÁFICAS
# ══════════════════════════════════════════════════════════════════════════════

def _lerp_rgb(c1, c2, t):
    t = 0.0 if t < 0 else 1.0 if t > 1 else t
    return (
        int(c1[0] + (c2[0] - c1[0]) * t),
        int(c1[1] + (c2[1] - c1[1]) * t),
        int(c1[2] + (c2[2] - c1[2]) * t),
    )


def _rgb_hex(r, g, b):
    return f"#{r:02x}{g:02x}{b:02x}"


# ══════════════════════════════════════════════════════════════════════════════
#  LÓGICA DE SESIONES
# ══════════════════════════════════════════════════════════════════════════════

def find_claude_dir():
    candidates = [
        Path.home() / ".claude",
        Path.home() / "AppData" / "Roaming" / "Claude",
        Path.home() / "Library" / "Application Support" / "Claude",
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


def decode_project_path(encoded: str) -> str:
    return encoded.replace("-", "/").replace("//", " → ")


def short_project_name(label: str) -> str:
    """Devuelve solo el nombre de la carpeta final del proyecto.

    El `label` ya viene decodificado (p. ej. 'D → Antigravity/Proyects/Moodie').
    Tomamos el último componente tras separar por '/' o ' → '.
    """
    name = label.replace(" → ", "/")
    name = name.rstrip("/")
    last = name.rsplit("/", 1)[-1] if "/" in name else name
    return last.strip() or label


def format_ts(ts_str: str) -> str:
    if not ts_str:
        return "—"
    try:
        dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d  %H:%M")
    except Exception:
        return ts_str[:16]


def extract_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                btype = block.get("type", "")
                if btype == "text":
                    parts.append(block.get("text", ""))
                elif btype == "tool_use":
                    name = block.get("name", "tool")
                    inp  = block.get("input", {})
                    parts.append(f"```tool:{name}\n{json.dumps(inp, indent=2, ensure_ascii=False)}\n```")
                elif btype == "tool_result":
                    res = block.get("content", "")
                    if isinstance(res, list):
                        res = "\n".join(b.get("text", "") for b in res if isinstance(b, dict))
                    parts.append(f"```tool_result\n{res}\n```")
        return "\n\n".join(p for p in parts if p)
    if isinstance(content, dict):
        return extract_text(content.get("content", ""))
    return ""


def load_session_metadata(jsonl_path: Path):
    messages, first_ts, last_ts, first_user_msg = [], None, None, ""
    ai_title, cwd = "", ""
    try:
        with open(jsonl_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    messages.append(obj)
                    ts = obj.get("timestamp")
                    if ts:
                        if first_ts is None:
                            first_ts = ts
                        last_ts = ts
                    # Nombre real de la sesión (título que Claude Code muestra en Recents)
                    if not ai_title and obj.get("type") == "ai-title":
                        ai_title = (obj.get("aiTitle") or "").strip()
                    # Ruta real del proyecto (no la del nombre de carpeta codificado)
                    if not cwd and obj.get("cwd"):
                        cwd = obj.get("cwd")
                    if not first_user_msg:
                        role    = obj.get("type") or obj.get("role", "")
                        content = obj.get("message", {}) if isinstance(obj.get("message"), dict) else {}
                        if role == "user" and content:
                            raw = content.get("content", "")
                            if isinstance(raw, list):
                                for block in raw:
                                    if isinstance(block, dict) and block.get("type") == "text":
                                        first_user_msg = block.get("text", "")[:140]
                                        break
                            elif isinstance(raw, str):
                                first_user_msg = raw[:140]
                except json.JSONDecodeError:
                    continue
    except Exception:
        return None
    if not messages:
        return None
    return {
        "path": jsonl_path,
        "session_id": jsonl_path.stem,
        "message_count": len(messages),
        "first_ts": first_ts,
        "last_ts": last_ts,
        "first_user_msg": first_user_msg or "(sin texto)",
        "title": ai_title,
        "cwd": cwd,
        "raw_messages": messages,
    }


def gather_all_sessions(projects_dir: Path):
    sessions = []
    for project_folder in sorted(projects_dir.iterdir()):
        if not project_folder.is_dir():
            continue
        fallback_label = decode_project_path(project_folder.name)  # solo si no hay cwd
        for jsonl_file in sorted(project_folder.glob("*.jsonl")):
            meta = load_session_metadata(jsonl_file)
            if meta:
                cwd = (meta.get("cwd") or "").strip()
                if cwd:
                    # Ruta REAL leída del .jsonl → nombre de carpeta correcto y sin ambigüedad
                    meta["project_full"] = cwd
                    meta["project"]      = Path(cwd).name
                else:
                    meta["project_full"] = fallback_label
                    meta["project"]      = short_project_name(fallback_label)
                # Lo que se muestra en la columna "Sesión": el título; si no hay, el primer mensaje
                meta["display_name"] = meta.get("title") or meta.get("first_user_msg") or "(sin título)"
                sessions.append(meta)
    sessions.sort(key=lambda s: s.get("last_ts") or "", reverse=True)

    # ── Deduplicación: replica el comportamiento del panel "Recents" de Claude Code ──
    # Si varias sesiones del MISMO proyecto (ruta completa) comparten el mismo primer
    # mensaje de usuario, es la misma conversación (reiniciada/duplicada). Conservamos
    # solo la más reciente, que ya quedó primera al ordenar por last_ts desc.
    seen: set = set()
    deduped = []
    for s in sessions:
        key = (s["project_full"], (s["first_user_msg"] or "")[:80].strip().lower())
        if key not in seen:
            seen.add(key)
            deduped.append(s)
    return deduped


def session_to_markdown(meta: dict) -> str:
    lines = [
        "# Sesión Claude Code",
        "",
        f"> **Sesión:** {meta.get('display_name') or meta.get('title') or '—'}  ",
        f"> **Proyecto:** `{meta['project']}`  ",
        f"> **Session ID:** `{meta['session_id']}`  ",
        f"> **Inicio:** {format_ts(meta.get('first_ts'))}  ",
        f"> **Última actividad:** {format_ts(meta.get('last_ts'))}  ",
        f"> **Mensajes totales:** {meta['message_count']}",
        "",
        "---",
        "",
    ]
    turn = 0
    for obj in meta["raw_messages"]:
        role = obj.get("type") or obj.get("role", "")
        msg  = obj.get("message", obj) if isinstance(obj.get("message"), dict) else obj
        if role == "user":
            text = extract_text(msg.get("content", "")).strip() if isinstance(msg, dict) else ""
            if not text:
                continue
            turn += 1
            lines += [f"## 🧑 Usuario — turno {turn}", "", text, "", "---", ""]
        elif role == "assistant":
            text = extract_text(msg.get("content", "")).strip() if isinstance(msg, dict) else ""
            if not text:
                continue
            lines += ["## 🤖 Claude", "", text, "", "---", ""]
        elif role == "system":
            text = extract_text(msg.get("content", "")).strip() if isinstance(msg, dict) else ""
            if text:
                lines += ["## ⚙️ System", "", f"> {text}", "", "---", ""]
    lines.append(f"*Exportado el {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} con Claude Code Session Exporter*")
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
#  ACCESO DIRECTO EN ESCRITORIO (Windows)
# ══════════════════════════════════════════════════════════════════════════════

def create_shortcut_windows(script_path: Path, icon_path: Path = None):
    """Crea un .lnk en el escritorio usando PowerShell."""
    desktop = Path.home() / "Desktop"
    if not desktop.exists():
        desktop = Path.home() / "OneDrive" / "Escritorio"
    if not desktop.exists():
        desktop = Path.home() / "OneDrive" / "Desktop"

    shortcut = desktop / "Claude Session Exporter.lnk"

    python_exe = Path(sys.executable)
    pythonw    = python_exe.parent / "pythonw.exe"
    if not pythonw.exists():
        pythonw = python_exe

    icon_line = f'$Shortcut.IconLocation = "{icon_path}"' if (icon_path and icon_path.exists()) else ""

    ps_script = f"""
$WS = New-Object -ComObject WScript.Shell
$Shortcut = $WS.CreateShortcut('{shortcut}')
$Shortcut.TargetPath = '{pythonw}'
$Shortcut.Arguments = '"{script_path}"'
$Shortcut.WorkingDirectory = '{script_path.parent}'
$Shortcut.Description = 'Exportar sesiones de Claude Code a Markdown'
{icon_line}
$Shortcut.Save()
"""
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps_script],
        capture_output=True, text=True
    )
    return shortcut if result.returncode == 0 else None


# ══════════════════════════════════════════════════════════════════════════════
#  ICONO EMBEBIDO (ICO en base64)
# ══════════════════════════════════════════════════════════════════════════════

ICON_B64 = "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"


# ══════════════════════════════════════════════════════════════════════════════
#  WIDGETS PERSONALIZADOS
# ══════════════════════════════════════════════════════════════════════════════

class RoundedButton(tk.Button):
    """Botón plano con jerarquía visual (compatible con tkinter en Windows).

    variant="primary"   → fondo ACCENT + texto TEXT  (llamada a la acción principal).
    variant="secondary" → fondo BG3 + texto ACCENT2, con borde que se ilumina a
                          ACCENT2 al pasar el mouse (sin robar protagonismo).
    """
    def __init__(self, parent, text, command, variant="primary", font_size=10, **kwargs):
        self._variant  = variant
        self._cmd_real = command
        bg, fg, border = self._palette(variant)
        self._bg_normal     = bg
        self._border_normal = border
        self._bg_hover      = bg if variant == "secondary" else self._lighten(bg, 30)
        self._border_hover  = ACCENT2 if variant == "secondary" else self._lighten(bg, 30)
        super().__init__(
            parent, text=text, command=command,
            bg=bg, fg=fg,
            activebackground=self._bg_hover, activeforeground=fg,
            disabledforeground=TEXT_DIM,
            font=("Segoe UI", font_size, "bold"),
            relief="flat", bd=0, cursor="hand2",
            padx=14, pady=9, takefocus=0,
            highlightthickness=1, highlightbackground=border, highlightcolor=border,
            **kwargs
        )
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)

    @staticmethod
    def _palette(variant):
        if variant == "secondary":
            return BG3, ACCENT2, BORDER
        return ACCENT, TEXT, ACCENT          # primary

    @staticmethod
    def _lighten(hex_color, amount=30):
        r = min(255, int(hex_color[1:3], 16) + amount)
        g = min(255, int(hex_color[3:5], 16) + amount)
        b = min(255, int(hex_color[5:7], 16) + amount)
        return f"#{r:02x}{g:02x}{b:02x}"

    def _on_enter(self, _):
        if str(self["state"]) == "disabled":
            return
        self.config(bg=self._bg_hover,
                    highlightbackground=self._border_hover,
                    highlightcolor=self._border_hover)

    def _on_leave(self, _):
        if str(self["state"]) == "disabled":
            return
        self.config(bg=self._bg_normal,
                    highlightbackground=self._border_normal,
                    highlightcolor=self._border_normal)

    def set_text(self, text):
        self.config(text=text)

    def set_state(self, enabled: bool):
        if enabled:
            bg, fg, border = self._palette(self._variant)
            self._bg_normal     = bg
            self._border_normal = border
            self._bg_hover      = bg if self._variant == "secondary" else self._lighten(bg, 30)
            self._border_hover  = ACCENT2 if self._variant == "secondary" else self._lighten(bg, 30)
            self.config(state="normal", bg=bg, fg=fg,
                        highlightbackground=border, highlightcolor=border,
                        command=self._cmd_real)
        else:
            self.config(state="disabled", bg=BG3, fg=TEXT_DIM,
                        highlightbackground=BORDER, highlightcolor=BORDER)


class StatusBar(tk.Frame):
    def __init__(self, parent):
        super().__init__(parent, bg=BG2, height=32)
        self._dot  = tk.Label(self, text="●", font=("Segoe UI", 10), bg=BG2, fg=TEXT_DIM)
        self._msg  = tk.Label(self, text="Listo", font=("Segoe UI", 9),
                               bg=BG2, fg=TEXT_DIM, anchor="w")
        self._dot.pack(side="left", padx=(12, 4))
        self._msg.pack(side="left", fill="x", expand=True)

    def set(self, text, color=TEXT_DIM):
        self._msg.config(text=text, fg=color)
        self._dot.config(fg=color)
        self.update_idletasks()

    def ok(self, text):    self.set(f"✔  {text}", SUCCESS)
    def info(self, text):  self.set(f"→  {text}", ACCENT2)
    def warn(self, text):  self.set(f"⚠  {text}", WARNING)
    def error(self, text): self.set(f"✖  {text}", DANGER)
    def spin(self, text):  self.set(f"◌  {text}", ACCENT)


# ══════════════════════════════════════════════════════════════════════════════
#  IDENTIDAD DE APP EN WINDOWS (para que el icono aparezca en la barra de tareas)
# ══════════════════════════════════════════════════════════════════════════════

def _set_app_user_model_id():
    """Sin esto, Windows agrupa el proceso bajo el icono genérico de pythonw.exe.
    Al fijar un AppUserModelID propio, la barra de tareas usa el icono de la ventana."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "JF012.ClaudeCodeSessionExporter")
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════════════════════
#  VENTANA PRINCIPAL
# ══════════════════════════════════════════════════════════════════════════════

class App(tk.Tk):
    def __init__(self):
        _set_app_user_model_id()
        super().__init__()
        self.title("Claude Code Session Exporter")
        self.configure(bg=BG)
        self.resizable(True, True)
        self.minsize(820, 540)

        self.update_idletasks()
        W, H = 920, 620
        x = (self.winfo_screenwidth()  - W) // 2
        y = (self.winfo_screenheight() - H) // 2
        self.geometry(f"{W}x{H}+{x}+{y}")

        # Icono embebido (ICO en base64) → ventana + barra de tareas + diálogos
        self._icon_path = self._extract_icon()
        if self._icon_path:
            try:
                self.iconbitmap(default=str(self._icon_path))
            except Exception:
                try:
                    self.iconbitmap(str(self._icon_path))
                except Exception:
                    pass

        self._sessions    = []
        self._out_dir     = Path(r"D:\Claude Code sessions")
        self._sort_col    = "last_ts"
        self._sort_rev    = True
        self._shimmer_pos = -220

        self._build_ui()
        self._load_sessions()

        if sys.platform == "win32":
            self.after(800, self._maybe_offer_shortcut)

    # ── Icono embebido ────────────────────────────────────────────────────────

    def _extract_icon(self):
        """Escribe el ICO embebido a una ruta estable (junto al script) para que el
        acceso directo y el icono a nivel de archivo sean persistentes; si no se puede
        escribir ahí, cae a %TEMP%."""
        import base64, tempfile
        try:
            ico_data = base64.b64decode(ICON_B64)
        except Exception:
            return None
        candidates = []
        try:
            candidates.append(Path(__file__).resolve().parent / "exporter_icon.ico")
        except Exception:
            pass
        candidates.append(Path(tempfile.gettempdir()) / "claude_exporter.ico")
        for target in candidates:
            try:
                if not target.exists() or target.stat().st_size != len(ico_data):
                    target.write_bytes(ico_data)
                return target
            except Exception:
                continue
        return None

    # ── Construcción de la UI ─────────────────────────────────────────────────

    def _build_ui(self):
        self._init_style()

        # ── Header animado (Canvas: gradiente morado→azul + shimmer) ─────────
        self._header = tk.Canvas(self, height=66, highlightthickness=0, bd=0, bg=ACCENT)
        self._header.pack(side="top", fill="x")
        self._header.create_text(22, 33, text="⬡", font=("Segoe UI", 22),
                                 fill="#ffffff", anchor="w", tags="content")
        self._header.create_text(56, 25, text="Claude Code Session Exporter",
                                 font=("Segoe UI", 14, "bold"), fill="#ffffff",
                                 anchor="w", tags="content")
        self._header.create_text(56, 45, text="Exporta cualquier sesión de Claude Code a Markdown",
                                 font=("Segoe UI", 9), fill="#e3e6fb", anchor="w", tags="content")
        self._header.bind("<Configure>", lambda e: self._draw_header_gradient())

        # Borde inferior del header: línea de gradiente del acento
        self._hdr_border = tk.Canvas(self, height=2, highlightthickness=0, bd=0, bg=ACCENT)
        self._hdr_border.pack(side="top", fill="x")
        self._hdr_border.bind("<Configure>", lambda e: self._draw_gradient_border())

        # ── Status bar (abajo del todo; el borde va justo encima) ────────────
        self._status = StatusBar(self)
        self._status.pack(side="bottom", fill="x")
        tk.Frame(self, bg=BORDER, height=1).pack(side="bottom", fill="x")

        # ── Cuerpo dividido: Sidebar (BG2) │ separador 1px │ Grid (BG) ───────
        body = tk.Frame(self, bg=BG)
        body.pack(side="top", fill="both", expand=True)

        sidebar = tk.Frame(body, bg=BG2, width=288)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)
        tk.Frame(body, bg=BORDER, width=1).pack(side="left", fill="y")   # separador sutil
        main = tk.Frame(body, bg=BG)
        main.pack(side="left", fill="both", expand=True)

        self._build_sidebar(sidebar)
        self._build_main(main)

        # Arrancar la animación del shimmer del header
        self.after(250, self._animate_shimmer)

    # ── Estilos ttk (configurar antes de instanciar los widgets) ──────────────

    def _init_style(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        # Data grid sobre el fondo más oscuro (BG)
        style.configure("Split.Treeview",
                        background=BG, fieldbackground=BG, foreground=TEXT,
                        rowheight=34, font=("Segoe UI", 10), borderwidth=0)
        # Encabezados: BG2, texto atenuado en mayúsculas/negrita
        style.configure("Split.Treeview.Heading",
                        background=BG2, foreground=TEXT_DIM,
                        font=("Segoe UI", 8, "bold"), relief="flat",
                        borderwidth=0, padding=(10, 10))
        style.map("Split.Treeview",
                  background=[("selected", ACCENT)],
                  foreground=[("selected", "#ffffff")])
        style.map("Split.Treeview.Heading",
                  background=[("active", BG3)], foreground=[("active", TEXT)])
        # Scrollbar oscuro acorde a la paleta
        style.configure("Dark.Vertical.TScrollbar",
                        background=BG3, troughcolor=BG, bordercolor=BG,
                        arrowcolor=TEXT_DIM, relief="flat")
        style.map("Dark.Vertical.TScrollbar", background=[("active", BORDER)])

    # ── Panel de controles (sidebar) ──────────────────────────────────────────

    def _build_sidebar(self, parent):
        sb = tk.Frame(parent, bg=BG2)
        sb.pack(fill="both", expand=True, padx=15, pady=15)

        def section(text):
            tk.Label(sb, text=text, bg=BG2, fg=TEXT_DIM,
                     font=("Segoe UI", 8, "bold")).pack(anchor="w", pady=(0, 6))

        # ── Filtros ──────────────────────────────────────────────────────
        section("F I L T R O S")
        self._search_var   = tk.StringVar()
        self._search_ph    = "Buscar nombre, proyecto o fecha…"
        self._search_is_ph = False
        self._search_entry = tk.Entry(
            sb, textvariable=self._search_var, font=("Segoe UI", 10),
            bg=BG3, fg=TEXT, insertbackground=ACCENT, relief="flat",
            highlightthickness=1, highlightbackground=BORDER, highlightcolor=ACCENT)
        self._search_entry.pack(fill="x", ipady=6)
        self._search_var.trace_add("write", lambda *_: self._filter_sessions())
        self._search_entry.bind("<FocusIn>",  self._search_focus_in)
        self._search_entry.bind("<FocusOut>", self._search_focus_out)
        self._apply_search_placeholder()

        # ── Exportación ──────────────────────────────────────────────────
        tk.Frame(sb, bg=BG2, height=18).pack()
        section("E X P O R T A C I Ó N")
        tk.Label(sb, text="Guardar en", bg=BG2, fg=TEXT_DIM,
                 font=("Segoe UI", 9)).pack(anchor="w")
        self._dir_var = tk.StringVar(value=str(self._out_dir))
        self._dir_entry = tk.Entry(
            sb, textvariable=self._dir_var, font=("Consolas", 9),
            bg=BG3, fg=TEXT, insertbackground=ACCENT, relief="flat",
            highlightthickness=1, highlightbackground=BORDER, highlightcolor=ACCENT)
        self._dir_entry.pack(fill="x", ipady=5, pady=(4, 8))
        RoundedButton(sb, "📁  Explorar carpeta", self._pick_dir,
                      variant="secondary", font_size=9).pack(fill="x")

        # Opción: abrir carpeta al terminar (toggle propio para verse limpio)
        self._open_after = tk.BooleanVar(value=True)
        toggle_row = tk.Frame(sb, bg=BG2)
        toggle_row.pack(fill="x", pady=(12, 2))
        self._chk = tk.Label(toggle_row, text="☑", bg=BG2, fg=ACCENT2,
                             font=("Segoe UI", 12), cursor="hand2")
        self._chk.pack(side="left")
        chk_lbl = tk.Label(toggle_row, text="  Abrir carpeta al exportar",
                           bg=BG2, fg=TEXT_DIM, font=("Segoe UI", 9), cursor="hand2")
        chk_lbl.pack(side="left")
        self._chk.bind("<Button-1>", self._toggle_open_after)
        chk_lbl.bind("<Button-1>", self._toggle_open_after)

        tk.Label(sb, text="Formato:  Markdown (.md)", bg=BG2, fg=TEXT_DIM,
                 font=("Segoe UI", 9)).pack(anchor="w", pady=(2, 0))

        # Espaciador flexible: empuja las acciones al fondo del panel
        tk.Frame(sb, bg=BG2).pack(fill="both", expand=True)

        # ── Acciones ─────────────────────────────────────────────────────
        self._btn_export = RoundedButton(sb, "⬇   Exportar sesión", self._export,
                                         variant="primary", font_size=11)
        self._btn_export.pack(fill="x", ipady=2)
        self._btn_export.set_state(False)

        actions = tk.Frame(sb, bg=BG2)
        actions.pack(fill="x", pady=(8, 0))
        self._btn_reload = RoundedButton(actions, "↻  Actualizar", self._load_sessions,
                                         variant="secondary", font_size=9)
        self._btn_reload.pack(side="left", fill="x", expand=True, padx=(0, 4))
        self._btn_shortcut = RoundedButton(actions, "🔗  Acceso", self._create_shortcut,
                                           variant="secondary", font_size=9)
        self._btn_shortcut.pack(side="left", fill="x", expand=True, padx=(4, 0))

    # ── Área principal (data grid / Treeview) ─────────────────────────────────

    def _build_main(self, parent):
        wrap = tk.Frame(parent, bg=BG)
        wrap.pack(fill="both", expand=True, padx=15, pady=15)

        head = tk.Frame(wrap, bg=BG)
        head.pack(fill="x", pady=(0, 10))
        tk.Label(head, text="Sesiones de Claude Code", bg=BG, fg=TEXT,
                 font=("Segoe UI", 12, "bold")).pack(side="left")
        self._count_lbl = tk.Label(head, text="", bg=BG, fg=TEXT_DIM,
                                   font=("Segoe UI", 9))
        self._count_lbl.pack(side="right")

        table = tk.Frame(wrap, bg=BG)
        table.pack(fill="both", expand=True)

        cols = ("last_ts", "message_count", "project", "first_user_msg")
        headers = {
            "last_ts":        "ÚLTIMA ACTIVIDAD",
            "message_count":  "MSGS",
            "project":        "PROYECTO",
            "first_user_msg": "SESIÓN",
        }
        widths = {"last_ts": 150, "message_count": 60, "project": 165, "first_user_msg": 430}

        self._tree = ttk.Treeview(table, columns=cols, show="headings",
                                  style="Split.Treeview", selectmode="browse")
        for col in cols:
            self._tree.heading(col, text=headers[col],
                               command=lambda c=col: self._sort_by(c))
            anchor = "center" if col == "message_count" else "w"
            self._tree.column(col, width=widths[col], minwidth=44,
                              anchor=anchor, stretch=(col == "first_user_msg"))

        sb = ttk.Scrollbar(table, orient="vertical", command=self._tree.yview,
                           style="Dark.Vertical.TScrollbar")
        self._tree.configure(yscrollcommand=sb.set)
        self._tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        # Zebra striping: filas pares BG, impares BG3
        self._tree.tag_configure("even", background=BG)
        self._tree.tag_configure("odd",  background=BG3)
        self._tree.bind("<Double-1>", lambda e: self._export())
        self._tree.bind("<<TreeviewSelect>>", self._on_select)

        self._tip = _TreeTooltip(self._tree, self._tooltip_text_for)

    # ── Placeholder del buscador + toggle ─────────────────────────────────────

    def _apply_search_placeholder(self):
        if not self._search_var.get():
            self._search_is_ph = True
            self._search_entry.config(fg=TEXT_DIM)
            self._search_var.set(self._search_ph)

    def _search_focus_in(self, _):
        if self._search_is_ph:
            self._search_is_ph = False
            self._search_var.set("")
            self._search_entry.config(fg=TEXT)

    def _search_focus_out(self, _):
        if not self._search_var.get().strip():
            self._apply_search_placeholder()

    def _toggle_open_after(self, _=None):
        self._open_after.set(not self._open_after.get())
        on = self._open_after.get()
        self._chk.config(text="☑" if on else "☐", fg=ACCENT2 if on else TEXT_DIM)

    # ── Gradientes y animación ────────────────────────────────────────────────

    def _draw_header_gradient(self):
        c = self._header
        c.delete("gradient")
        w = c.winfo_width()
        h = c.winfo_height()
        if w <= 1 or h <= 1:
            return
        step = 4
        for x in range(0, w, step):
            t = x / max(w - 1, 1)
            r, g, b = _lerp_rgb(_ACCENT_RGB, _ACCENT2_RGB, t)
            c.create_rectangle(x, 0, x + step, h, fill=_rgb_hex(r, g, b),
                               outline="", tags="gradient")
        c.tag_lower("gradient")          # gradiente al fondo
        c.tag_raise("shimmer")           # shimmer encima del gradiente
        c.tag_raise("content")           # texto siempre arriba

    def _animate_shimmer(self):
        c = self._header
        if not c.winfo_exists():
            return
        w = c.winfo_width()
        h = c.winfo_height()
        if w <= 1 or h <= 1:
            self.after(100, self._animate_shimmer)
            return

        c.delete("shimmer")
        shimmer_w = 200
        self._shimmer_pos += 16

        if self._shimmer_pos > w + shimmer_w:
            # pausa breve antes de reiniciar el barrido
            self._shimmer_pos = -shimmer_w
            self.after(1200, self._animate_shimmer)
            return

        strips = 22
        strip_w = max(1, shimmer_w // strips)
        sx = self._shimmer_pos
        for i in range(strips):
            x = sx + i * strip_w
            if x + strip_w < 0 or x >= w:
                continue
            t = x / max(w - 1, 1)
            base = _lerp_rgb(_ACCENT_RGB, _ACCENT2_RGB, t)
            glow = math.sin((i / max(strips - 1, 1)) * math.pi)   # 0→1→0
            boost = int(glow * 38)
            col = (min(255, base[0] + boost),
                   min(255, base[1] + boost),
                   min(255, base[2] + boost))
            c.create_rectangle(max(0, x), 0, min(w, x + strip_w), h,
                               fill=_rgb_hex(*col), outline="", tags="shimmer")

        c.tag_raise("content")
        self.after(50, self._animate_shimmer)

    def _draw_gradient_border(self):
        c = self._hdr_border
        c.delete("all")
        w = c.winfo_width()
        if w <= 1:
            return
        step = 4
        for x in range(0, w, step):
            t = x / max(w - 1, 1)
            r, g, b = _lerp_rgb(_ACCENT_RGB, _ACCENT2_RGB, t)
            c.create_rectangle(x, 0, x + step, 2, fill=_rgb_hex(r, g, b), outline="")

    # ── Tooltip ───────────────────────────────────────────────────────────────

    def _tooltip_text_for(self, session_id):
        for s in self._sessions:
            if s["session_id"] == session_id:
                return s.get("project_full", s.get("project", ""))
        return ""

    # ── Carga y filtrado ──────────────────────────────────────────────────────

    def _load_sessions(self):
        self._status.spin("Buscando sesiones de Claude Code…")
        self._btn_export.set_state(False)

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
            sessions = gather_all_sessions(projects)
            self.after(0, lambda: self._on_sessions_loaded(sessions))

        threading.Thread(target=worker, daemon=True).start()

    def _on_sessions_loaded(self, sessions):
        self._sessions = sessions
        self._filter_sessions()
        n = len(sessions)
        if n == 0:
            self._status.warn("No se encontraron sesiones guardadas")
        else:
            self._status.ok(
                f"{n} sesión{'es' if n != 1 else ''} vigente{'s' if n != 1 else ''}"
                f" encontrada{'s' if n != 1 else ''}"
            )

    def _filter_sessions(self):
        if not hasattr(self, "_tree"):
            return
        q = "" if getattr(self, "_search_is_ph", False) else self._search_var.get().lower().strip()
        visible = [
            s for s in self._sessions
            if not q
            or q in s["project"].lower()
            or q in s.get("project_full", "").lower()
            or q in s.get("display_name", "").lower()
            or q in s["first_user_msg"].lower()
            or q in format_ts(s.get("last_ts")).lower()
        ]
        self._populate_tree(visible)
        if getattr(self, "_count_lbl", None) is not None:
            self._count_lbl.config(
                text=f"{len(visible)} / {len(self._sessions)}" if q
                     else f"{len(self._sessions)} sesiones"
            )

    def _populate_tree(self, sessions):
        self._tree.delete(*self._tree.get_children())
        for i, s in enumerate(sessions):
            tag  = "even" if i % 2 == 0 else "odd"
            msgs = str(s["message_count"])
            proj = s["project"]
            snip = (s.get("display_name") or s.get("first_user_msg") or "").replace("\n", " ")
            self._tree.insert("", "end", iid=s["session_id"],
                              values=(format_ts(s.get("last_ts")), msgs, proj, snip),
                              tags=(tag,))

    def _on_select(self, _):
        self._btn_export.set_state(bool(self._tree.selection()))

    def _sort_by(self, col):
        if self._sort_col == col:
            self._sort_rev = not self._sort_rev
        else:
            self._sort_col = col
            self._sort_rev = True
        key_field = "display_name" if col == "first_user_msg" else col
        self._sessions.sort(key=lambda s: (str(s.get(key_field) or "")), reverse=self._sort_rev)
        self._filter_sessions()

    # ── Acciones ──────────────────────────────────────────────────────────────

    def _pick_dir(self):
        chosen = filedialog.askdirectory(
            title="Selecciona la carpeta de destino",
            initialdir=self._dir_var.get()
        )
        if chosen:
            self._out_dir = Path(chosen)
            self._dir_var.set(chosen)

    def _get_selected_session(self):
        sel = self._tree.selection()
        if not sel:
            return None
        sid = sel[0]
        for s in self._sessions:
            if s["session_id"] == sid:
                return s
        return None

    def _export(self):
        session = self._get_selected_session()
        if not session:
            self._status.warn("Selecciona una sesión primero")
            return

        out_dir = Path(self._dir_var.get())
        try:
            out_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            self._status.error(f"No se puede crear la carpeta: {e}")
            return

        self._status.spin("Exportando…")
        self._btn_export.set_state(False)

        def worker():
            try:
                md = session_to_markdown(session)
                ts_part  = format_ts(session.get("last_ts")).replace(":", "-").replace(" ", "_").strip()
                sid_part = session["session_id"][:8]
                filename = f"claude_session_{ts_part}_{sid_part}.md"
                out_path = out_dir / filename
                out_path.write_text(md, encoding="utf-8")
                self.after(0, lambda: self._on_exported(out_path, md))
            except Exception as e:
                self.after(0, lambda: self._status.error(f"Error al exportar: {e}"))
                self.after(0, lambda: self._btn_export.set_state(True))

        threading.Thread(target=worker, daemon=True).start()

    def _on_exported(self, out_path: Path, content: str):
        self._btn_export.set_state(True)
        size_kb = len(content.encode("utf-8")) / 1024
        has_turns = ("## 🧑" in content) or ("## 🤖" in content)
        if has_turns:
            self._status.ok(f"Exportación completada → {out_path.name}  ({size_kb:.1f} KB)")
        else:
            self._status.warn(f"Sesión sin contenido legible → {out_path.name}")
        if self._open_after.get():
            self._open_folder(out_path.parent)

    def _open_folder(self, path: Path):
        try:
            if sys.platform == "win32":
                os.startfile(path)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except Exception:
            pass

    # ── Acceso directo ────────────────────────────────────────────────────────

    def _maybe_offer_shortcut(self):
        flag = Path.home() / ".claude_exporter_shortcut_created"
        if flag.exists():
            return
        if messagebox.askyesno(
            "Acceso directo",
            "¿Quieres crear un acceso directo en el Escritorio\n"
            "para abrir esta aplicación con un solo clic?",
            icon="question"
        ):
            self._create_shortcut(silent=False)
            flag.touch()

    def _create_shortcut(self, silent=True):
        if sys.platform != "win32":
            self._status.warn("Acceso directo solo disponible en Windows")
            return
        script_path = Path(__file__).resolve()
        result = create_shortcut_windows(script_path, self._icon_path)
        if result:
            self._status.ok("Acceso directo creado en el Escritorio")
            if not silent:
                messagebox.showinfo(
                    "Acceso directo creado",
                    f"✔  Acceso directo creado:\n{result}\n\n"
                    "Desde ahora puedes abrirlo desde el Escritorio."
                )
        else:
            self._status.error("No se pudo crear el acceso directo")
            if not silent:
                messagebox.showerror(
                    "Error",
                    "No se pudo crear el acceso directo.\n"
                    "Asegúrate de que PowerShell esté disponible."
                )


# ══════════════════════════════════════════════════════════════════════════════
#  TOOLTIP PARA EL TREEVIEW (muestra la ruta completa del proyecto)
# ══════════════════════════════════════════════════════════════════════════════

class _TreeTooltip:
    def __init__(self, tree: ttk.Treeview, text_getter):
        self._tree = tree
        self._get  = text_getter
        self._tip  = None
        self._row  = None
        tree.bind("<Motion>", self._on_motion)
        tree.bind("<Leave>", lambda e: self._hide())

    def _on_motion(self, event):
        row = self._tree.identify_row(event.y)
        if row != self._row:
            self._row = row
            self._hide()
            if row:
                text = self._get(row)
                if text:
                    self._show(text, event.x_root, event.y_root)

    def _show(self, text, x, y):
        self._tip = tk.Toplevel(self._tree)
        self._tip.wm_overrideredirect(True)
        self._tip.wm_geometry(f"+{x + 14}+{y + 12}")
        self._tip.configure(bg=BORDER)               # marco de 1px (BORDER)
        tk.Label(self._tip, text=text, font=("Consolas", 9),
                 bg=BG3, fg=TEXT, padx=8, pady=4,
                 relief="flat", bd=0).pack(padx=1, pady=1)

    def _hide(self):
        if self._tip is not None:
            try:
                self._tip.destroy()
            except Exception:
                pass
            self._tip = None


# ══════════════════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    app = App()
    app.mainloop()
