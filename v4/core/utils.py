"""
core/utils.py — Utilidades transversales sin estado.

Agrupa cuatro familias de helpers que no encajan en sessions/exporter:
  1. Color / gráficos  (interpolación, aclarar, chip por proyecto)
  2. Rutas y formato    (localizar ~/.claude, nombres de proyecto, timestamps)
  3. Plataforma Windows (AppUserModelID, icono embebido, abrir carpeta, shortcut)
"""
import os
import sys
import base64
import zlib
import tempfile
import subprocess
from datetime import datetime
from pathlib import Path

from styles import CHIP_COLORS, BG_PANEL, ICON_B64


# ══════════════════════════════════════════════════════════════════════════════
#  1. COLOR / GRÁFICOS
# ══════════════════════════════════════════════════════════════════════════════

def _hex_to_rgb(h: str):
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def rgb_hex(r, g, b) -> str:
    return f"#{int(r):02x}{int(g):02x}{int(b):02x}"


def lerp_rgb(c1, c2, t: float):
    """Interpola dos colores RGB (tuplas) con factor t∈[0,1]."""
    t = 0.0 if t < 0 else 1.0 if t > 1 else t
    return (
        int(c1[0] + (c2[0] - c1[0]) * t),
        int(c1[1] + (c2[1] - c1[1]) * t),
        int(c1[2] + (c2[2] - c1[2]) * t),
    )


def mix(hex_a: str, hex_b: str, t: float) -> str:
    """Mezcla dos colores hex; t=0 → hex_a, t=1 → hex_b."""
    return rgb_hex(*lerp_rgb(_hex_to_rgb(hex_a), _hex_to_rgb(hex_b), t))


def lighten(hex_color: str, amount: int = 30) -> str:
    r, g, b = _hex_to_rgb(hex_color)
    return rgb_hex(min(255, r + amount), min(255, g + amount), min(255, b + amount))


def color_for_project(key: str):
    """Color estable (no aleatorio entre ejecuciones) para el chip de un proyecto.

    Devuelve (fg, bg): un tono brillante para el texto y un fondo oscuro y discreto
    obtenido mezclando ese tono hacia el color de panel.
    """
    if not key:
        fg = CHIP_COLORS[0]
    else:
        fg = CHIP_COLORS[zlib.crc32(key.encode("utf-8")) % len(CHIP_COLORS)]
    return fg, mix(fg, BG_PANEL, 0.80)


# ══════════════════════════════════════════════════════════════════════════════
#  2. RUTAS Y FORMATO
# ══════════════════════════════════════════════════════════════════════════════

def find_claude_dir():
    """Localiza la carpeta de configuración de Claude Code en cada plataforma."""
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
    """Decodifica el nombre de carpeta codificado por Claude Code (fallback)."""
    return encoded.replace("-", "/").replace("//", " → ")


def short_project_name(label: str) -> str:
    """Último componente de una ruta de proyecto ya decodificada."""
    name = label.replace(" → ", "/").rstrip("/")
    last = name.rsplit("/", 1)[-1] if "/" in name else name
    return last.strip() or label


def format_ts(ts_str: str) -> str:
    """Formatea un timestamp ISO a 'YYYY-MM-DD  HH:MM' (o '—' si falta)."""
    if not ts_str:
        return "—"
    try:
        dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d  %H:%M")
    except Exception:
        return ts_str[:16]


# ══════════════════════════════════════════════════════════════════════════════
#  3. PLATAFORMA / RECURSOS (Windows)
# ══════════════════════════════════════════════════════════════════════════════

def get_base_path() -> Path:
    """Directorio base de recursos: el bundle de PyInstaller (sys._MEIPASS) si
    está congelado, o la carpeta del proyecto al ejecutar desde fuente."""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent.parent  # .../v4


def set_app_user_model_id(app_id: str = "JF012.ClaudeCodeSessionExporter"):
    """Fija un AppUserModelID propio para que la barra de tareas de Windows use
    el icono de la ventana en lugar del genérico de pythonw.exe."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    except Exception:
        pass


def extract_icon():
    """Materializa el ICO embebido a una ruta estable y devuelve su Path.

    Preferimos escribirlo junto al proyecto (icono persistente para el shortcut);
    si no se puede, caemos a %TEMP%. Devuelve None si algo falla.
    """
    try:
        ico_data = base64.b64decode(ICON_B64)
    except Exception:
        return None

    candidates = []
    if getattr(sys, "frozen", False):
        candidates.append(Path(tempfile.gettempdir()) / "claude_exporter.ico")
    else:
        try:
            candidates.append(get_base_path() / "exporter_icon.ico")
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


def open_path(path: Path):
    """Abre una carpeta/archivo con el explorador del sistema."""
    try:
        if sys.platform == "win32":
            os.startfile(path)  # noqa: S606 (uso intencional en Windows)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
    except Exception:
        pass


def create_desktop_shortcut(entry_script: Path = None, icon_path: Path = None):
    """Crea un .lnk en el Escritorio (Windows) vía PowerShell.

    - Si la app está congelada (.exe), el acceso directo apunta al propio .exe.
    - Si se ejecuta desde fuente, apunta a pythonw.exe con el script de entrada.
    Devuelve el Path del shortcut creado, o None si falla.
    """
    if sys.platform != "win32":
        return None

    # Escritorio (cuenta normal u OneDrive, ES/EN)
    desktop = Path.home() / "Desktop"
    for alt in (Path.home() / "OneDrive" / "Escritorio",
                Path.home() / "OneDrive" / "Desktop"):
        if not desktop.exists():
            desktop = alt
    if not desktop.exists():
        desktop = Path.home() / "Desktop"

    shortcut = desktop / "Claude Session Exporter.lnk"

    if getattr(sys, "frozen", False):
        target  = Path(sys.executable)
        args    = ""
        workdir = target.parent
    else:
        python_exe = Path(sys.executable)
        pythonw    = python_exe.parent / "pythonw.exe"
        target  = pythonw if pythonw.exists() else python_exe
        script  = Path(entry_script).resolve()
        args    = f'"{script}"'
        workdir = script.parent

    icon_line = (f'$Shortcut.IconLocation = "{icon_path}"'
                 if (icon_path and Path(icon_path).exists()) else "")

    ps_script = f"""
$WS = New-Object -ComObject WScript.Shell
$Shortcut = $WS.CreateShortcut('{shortcut}')
$Shortcut.TargetPath = '{target}'
$Shortcut.Arguments = '{args}'
$Shortcut.WorkingDirectory = '{workdir}'
$Shortcut.Description = 'Exportar sesiones de Claude Code a Markdown'
{icon_line}
$Shortcut.Save()
"""
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_script],
            capture_output=True, text=True,
        )
        return shortcut if result.returncode == 0 else None
    except Exception:
        return None
