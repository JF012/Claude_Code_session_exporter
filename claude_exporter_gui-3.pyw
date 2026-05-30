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
        "raw_messages": messages,
    }


def gather_all_sessions(projects_dir: Path):
    sessions = []
    for project_folder in sorted(projects_dir.iterdir()):
        if not project_folder.is_dir():
            continue
        full_label = decode_project_path(project_folder.name)   # ruta completa decodificada
        proj_name  = short_project_name(full_label)             # solo el nombre de la carpeta
        for jsonl_file in sorted(project_folder.glob("*.jsonl")):
            meta = load_session_metadata(jsonl_file)
            if meta:
                meta["project"]      = proj_name    # ← lo que se muestra / exporta / busca
                meta["project_full"] = full_label   # ← ruta completa (clave de deduplicación)
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

ICON_B64 = "AAABAAEAEBAAAAAAIAAXAQAAFgAAAIlQTkcNChoKAAAADUlIRFIAAAAQAAAAEAgGAAAAH/P/YQAAAN5JREFUeJzNky0PglAUhh+cToOMQjE4KpuNrDPrz2AGfxLB+SMMmNnMZiozsDmK0wAzaOGyC1yuo3nS/Tjvcz/Oe0ATu+VnodsHMDqEU8Dx8ii4Ttb7cjk5XIxXJ6AUIYQA8WPmulYaA5SgBEAGGZIQL4/OQghwvG3f/jwcAahAMsDx8iiQhc2rdoGGclJWmPbpvkpV/yKgPmH1LICBKlkXWWHa8rw3oBl/BrDHz6wvoFYF10pjn/BHKeuH1IxEw4UCpPDApgKIgQ6ks3OrmeSeAJAaqtUHSkAHSCkG+AJuynW9pJLiBAAAAABJRU5ErkJggg=="


# ══════════════════════════════════════════════════════════════════════════════
#  WIDGETS PERSONALIZADOS
# ══════════════════════════════════════════════════════════════════════════════

class RoundedButton(tk.Button):
    """Botón estilizado compatible con Python 3.x / tkinter en Windows.

    Hover más brillante (+45 por canal) que el estado normal.
    """
    def __init__(self, parent, text, command, bg=ACCENT, fg=TEXT,
                 width=200, height=40, radius=10, font_size=11, **kwargs):
        self._bg_normal  = bg
        self._bg_hover   = self._lighten(bg, 45)
        self._bg_dis     = TEXT_DIM
        self._cmd_real   = command
        super().__init__(
            parent,
            text=text,
            command=command,
            bg=bg,
            fg=fg,
            activebackground=self._bg_hover,
            activeforeground=fg,
            font=("Segoe UI", font_size, "bold"),
            relief="flat",
            bd=0,
            cursor="hand2",
            padx=10,
            pady=4,
            **kwargs
        )
        self.bind("<Enter>", lambda e: self["state"] == "normal" and self.config(bg=self._bg_hover))
        self.bind("<Leave>", lambda e: self["state"] == "normal" and self.config(bg=self._bg_normal))

    @staticmethod
    def _lighten(hex_color, amount=45):
        r = min(255, int(hex_color[1:3], 16) + amount)
        g = min(255, int(hex_color[3:5], 16) + amount)
        b = min(255, int(hex_color[5:7], 16) + amount)
        return f"#{r:02x}{g:02x}{b:02x}"

    def set_text(self, text):
        self.config(text=text)

    def set_state(self, enabled: bool):
        if enabled:
            self._bg_normal = ACCENT
            self._bg_hover  = self._lighten(ACCENT, 45)
            self.config(state="normal", bg=ACCENT, command=self._cmd_real)
        else:
            self._bg_normal = self._bg_dis
            self.config(state="disabled", bg=self._bg_dis)


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
#  VENTANA PRINCIPAL
# ══════════════════════════════════════════════════════════════════════════════

class App(tk.Tk):
    def __init__(self):
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

        # Icono embebido (ICO en base64)
        self._icon_path = self._extract_icon()
        if self._icon_path:
            try:
                self.iconbitmap(str(self._icon_path))
            except Exception:
                pass

        self._sessions    = []
        self._out_dir     = Path(r"D:\Claude Code sessions")
        self._sort_col    = "last_ts"
        self._sort_rev    = True
        self._shimmer_pos = -220
        self._count_id    = None

        self._build_ui()
        self._load_sessions()

        if sys.platform == "win32":
            self.after(800, self._maybe_offer_shortcut)

    # ── Icono embebido ────────────────────────────────────────────────────────

    def _extract_icon(self):
        import base64, tempfile
        try:
            ico_data = base64.b64decode(ICON_B64)
            tmp = Path(tempfile.gettempdir()) / "claude_exporter.ico"
            tmp.write_bytes(ico_data)
            return tmp
        except Exception:
            return None

    # ── Construcción de la UI ─────────────────────────────────────────────────

    def _build_ui(self):
        # ── Header animado (Canvas: gradiente morado→azul + shimmer) ─────────
        self._header = tk.Canvas(self, height=64, highlightthickness=0, bd=0, bg=ACCENT)
        self._header.pack(side="top", fill="x")

        self._header.create_text(20, 32, text="⬡", font=("Segoe UI", 22),
                                 fill="#ffffff", anchor="w", tags="content")
        self._header.create_text(54, 24, text="Claude Code Session Exporter",
                                 font=("Segoe UI", 14, "bold"), fill="#ffffff",
                                 anchor="w", tags="content")
        self._header.create_text(54, 44, text="Selecciona una sesión y expórtala a Markdown",
                                 font=("Segoe UI", 9), fill="#e3e6fb", anchor="w", tags="content")

        self._btn_reload = RoundedButton(self._header, "↻  Recargar", self._load_sessions,
                                         bg=BG3, fg=TEXT, font_size=9)
        self._btn_reload.place(relx=1.0, rely=0.5, anchor="e", x=-14)

        self._header.bind("<Configure>", lambda e: self._draw_header_gradient())

        # ── Borde inferior del header: línea de gradiente del acento ─────────
        self._hdr_border = tk.Canvas(self, height=2, highlightthickness=0, bd=0, bg=ACCENT)
        self._hdr_border.pack(side="top", fill="x")
        self._hdr_border.bind("<Configure>", lambda e: self._draw_gradient_border())

        # ── Status bar (abajo del todo) ──────────────────────────────────────
        self._status = StatusBar(self)
        self._status.pack(side="bottom", fill="x")
        tk.Frame(self, bg=BORDER, height=1).pack(side="bottom", fill="x")

        # ── Panel inferior (carpeta destino + botones) ───────────────────────
        bottom = tk.Frame(self, bg=BG2, height=80)
        bottom.pack(side="bottom", fill="x")
        bottom.pack_propagate(False)

        dir_row = tk.Frame(bottom, bg=BG2)
        dir_row.pack(fill="x", padx=18, pady=(10, 4))
        tk.Label(dir_row, text="Guardar en:", font=("Segoe UI", 9),
                 bg=BG2, fg=TEXT_DIM).pack(side="left")
        self._dir_var = tk.StringVar(value=str(self._out_dir))
        dir_entry = tk.Entry(dir_row, textvariable=self._dir_var,
                             font=("Segoe UI", 9), bg=BG3, fg=TEXT,
                             insertbackground=ACCENT, relief="flat",
                             highlightthickness=1, highlightbackground=BORDER,
                             highlightcolor=ACCENT, width=52)
        dir_entry.pack(side="left", ipady=4, padx=(6, 4))
        RoundedButton(dir_row, "📁  Cambiar", self._pick_dir,
                      bg=BG3, fg=TEXT, font_size=9).pack(side="left")

        btn_row = tk.Frame(bottom, bg=BG2)
        btn_row.pack(anchor="e", padx=18)
        self._btn_shortcut = RoundedButton(btn_row, "🔗  Crear acceso directo",
                                           self._create_shortcut, bg="#2a2d45",
                                           fg=TEXT, font_size=9)
        self._btn_shortcut.pack(side="left", padx=(0, 10))
        self._btn_export = RoundedButton(btn_row, "⬇  Exportar sesión", self._export,
                                         bg=ACCENT, fg=TEXT, font_size=10)
        self._btn_export.pack(side="left")

        tk.Frame(self, bg=BORDER, height=1).pack(side="bottom", fill="x")

        # ── Cuerpo: Canvas con gradiente diagonal sutil (BG→BG2→BG3) ─────────
        #    Sobre él van el buscador y la tabla (la tabla mantiene fondo sólido).
        self._body = tk.Canvas(self, highlightthickness=0, bd=0, bg=BG)
        self._body.pack(side="top", fill="both", expand=True)
        self._body.bind("<Configure>", self._on_body_configure)

        # Buscador (sobre el gradiente)
        self._body.create_text(26, 30, text="🔍", font=("Segoe UI", 12),
                               fill=TEXT_DIM, anchor="w", tags="ui")
        self._search_var = tk.StringVar()
        self._search_var.trace_add("write", lambda *_: self._filter_sessions())
        entry = tk.Entry(self._body, textvariable=self._search_var,
                         font=("Segoe UI", 10), bg=BG3, fg=TEXT,
                         insertbackground=ACCENT, relief="flat",
                         highlightthickness=1, highlightbackground=BORDER,
                         highlightcolor=ACCENT)
        entry.place(x=48, y=14, relwidth=1.0, width=-210, height=32)
        self._count_id = self._body.create_text(0, 30, text="", anchor="e",
                                                font=("Segoe UI", 9), fill=TEXT_DIM,
                                                tags="ui")

        # Tabla de sesiones (frame opaco sobre el gradiente → legibilidad)
        table_frame = tk.Frame(self._body, bg=BG)
        table_frame.place(x=18, y=54, relwidth=1.0, width=-36,
                          relheight=1.0, height=-66)

        cols = ("last_ts", "message_count", "project", "first_user_msg")
        headers = {
            "last_ts":        "Última actividad",
            "message_count":  "Msgs",
            "project":        "Proyecto",
            "first_user_msg": "Primer mensaje",
        }
        col_widths = {
            "last_ts":        140,
            "message_count":  50,
            "project":        160,   # ← más angosto: ahora solo el nombre corto
            "first_user_msg": 430,
        }

        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("Dark.Treeview",
                        background=BG2, fieldbackground=BG2, foreground=TEXT,
                        rowheight=30, font=("Segoe UI", 10), borderwidth=0)
        style.configure("Dark.Treeview.Heading",
                        background=BG3, foreground=TEXT_DIM,
                        font=("Segoe UI", 9, "bold"), relief="flat", borderwidth=0)
        style.map("Dark.Treeview",
                  background=[("selected", ACCENT)],
                  foreground=[("selected", "#ffffff")])
        style.map("Dark.Treeview.Heading", background=[("active", BORDER)])

        self._tree = ttk.Treeview(table_frame, columns=cols, show="headings",
                                  style="Dark.Treeview", selectmode="browse")
        for col in cols:
            self._tree.heading(col, text=headers[col],
                               command=lambda c=col: self._sort_by(c))
            anchor = "center" if col == "message_count" else "w"
            self._tree.column(col, width=col_widths[col], minwidth=40,
                              anchor=anchor, stretch=(col == "first_user_msg"))

        sb = ttk.Scrollbar(table_frame, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=sb.set)
        self._tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        self._tree.tag_configure("odd",  background=BG2)
        self._tree.tag_configure("even", background=BG3)
        self._tree.bind("<Double-1>", lambda e: self._export())
        self._tree.bind("<<TreeviewSelect>>", self._on_select)

        # Tooltip con la ruta completa del proyecto (al pasar el mouse)
        self._tip = _TreeTooltip(self._tree, self._tooltip_text_for)

        # Arrancar la animación del shimmer del header
        self.after(250, self._animate_shimmer)

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

    def _on_body_configure(self, event=None):
        self._draw_body_gradient()
        if self._count_id is not None:
            w = self._body.winfo_width()
            self._body.coords(self._count_id, w - 18, 30)

    def _draw_body_gradient(self):
        c = self._body
        c.delete("grad")
        w = c.winfo_width()
        h = c.winfo_height()
        if w <= 1 or h <= 1:
            return
        step = 8
        for y in range(0, h, step):
            t = y / max(h - 1, 1)
            if t < 0.5:
                rgb = _lerp_rgb(_BG_RGB, _BG2_RGB, t * 2)
            else:
                rgb = _lerp_rgb(_BG2_RGB, _BG3_RGB, (t - 0.5) * 2)
            c.create_rectangle(0, y, w, y + step, fill=_rgb_hex(*rgb),
                               outline="", tags="grad")
        c.tag_lower("grad")        # gradiente debajo del texto del buscador
        c.tag_raise("ui")

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
        q = self._search_var.get().lower().strip()
        visible = [
            s for s in self._sessions
            if not q
            or q in s["project"].lower()
            or q in s.get("project_full", "").lower()
            or q in s["first_user_msg"].lower()
            or q in format_ts(s.get("last_ts")).lower()
        ]
        self._populate_tree(visible)
        if self._count_id is not None:
            self._body.itemconfig(
                self._count_id,
                text=f"{len(visible)} / {len(self._sessions)}" if q
                     else f"{len(self._sessions)} sesiones"
            )

    def _populate_tree(self, sessions):
        self._tree.delete(*self._tree.get_children())
        for i, s in enumerate(sessions):
            tag  = "even" if i % 2 == 0 else "odd"
            msgs = str(s["message_count"])
            proj = s["project"]
            snip = s["first_user_msg"].replace("\n", " ")
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
        self._sessions.sort(key=lambda s: (str(s.get(col) or "")), reverse=self._sort_rev)
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
        self._status.ok(f"Guardado → {out_path.name}  ({size_kb:.1f} KB)")
        if messagebox.askyesno(
            "¡Listo!",
            f"Sesión exportada exitosamente:\n\n{out_path}\n\n¿Abrir carpeta?",
            icon="info"
        ):
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
        tk.Label(self._tip, text=text, font=("Segoe UI", 9),
                 bg="#2a2d45", fg=TEXT, padx=8, pady=4,
                 relief="solid", bd=1).pack()

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
