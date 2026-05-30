"""
styles.py — Identidad visual de Claude Exporter v4.

Centraliza TODA la paleta de color, las fuentes, el icono embebido y la
configuración de estilos ttk. Ningún otro módulo debería hardcodear un color:
si algo se ve mal, se ajusta aquí.
"""
from tkinter import ttk


# ══════════════════════════════════════════════════════════════════════════════
#  PALETA — Glassmorphism Dark (índigo / violeta sobre negro azulado)
# ══════════════════════════════════════════════════════════════════════════════

# ── Superficies (de más oscuro a más elevado) ────────────────────────────────
BG_DEEP   = "#050810"   # fondo principal de la app y del área central (tabla)
BG_PANEL  = "#0d1117"   # paneles glass: sidebar, toolbar, inputs
BG_GLASS  = "#111827"   # vidrio elevado: panel de preview, tooltips
BG_ELEV   = "#161b2c"   # chip / badge discreto, botones flat

# ── Filas de la tabla (zebra striping muy sutil + estados) ───────────────────
ROW_EVEN  = "#070b15"   # fila par   (apenas por encima de BG_DEEP)
ROW_ODD   = "#0a0f1c"   # fila impar (zebra sutil)
ROW_HOVER = "#121a2e"   # fila bajo el cursor
ROW_SEL   = "#1a2342"   # fila seleccionada (glow índigo)

# ── Acentos ──────────────────────────────────────────────────────────────────
ACCENT        = "#6366f1"  # índigo principal (CTA, selección, foco)
ACCENT_SOFT   = "#818cf8"  # índigo claro (hover, detalles)
ACCENT_VIOLET = "#a78bfa"  # violeta suave (acentos secundarios)
PRIMARY_HOVER = "#4f46e5"  # hover del botón principal

# ── Semánticos (status bar) ──────────────────────────────────────────────────
SUCCESS = "#34d399"   # verde esmeralda
WARNING = "#fbbf24"   # ámbar
DANGER  = "#f87171"   # rojo suave

# ── Texto (de más brillante a más tenue) ─────────────────────────────────────
TEXT       = "#f1f5f9"   # principal
TEXT_SOFT  = "#cbd5e1"   # secundario claro (preview de sesión)
TEXT_MUTE  = "#94a3b8"   # slate (etiquetas, proyecto)
TEXT_DIM   = "#64748b"   # terciario (metadatos, fechas)
TEXT_FAINT = "#334155"   # placeholder / deshabilitado
SEL_TEXT   = "#dbe4ff"   # texto sobre fila seleccionada

# ── Bordes y líneas ──────────────────────────────────────────────────────────
BORDER      = "#1e293b"   # borde sutil de paneles e inputs
BORDER_SOFT = "#141c2b"   # separadores casi invisibles
BORDER_FOCUS= ACCENT      # focus ring de inputs

# ── Chips / badges discretos ─────────────────────────────────────────────────
CHIP_BG     = "#161b2c"
CHIP_BORDER = "#2a3149"
CHIP_HOVER  = "#1e2540"

# ── Gradiente del logo (glow índigo en el sidebar) ───────────────────────────
GLOW_TOP_RGB = (12, 16, 32)    # casi negro azulado
GLOW_BOT_RGB = (40, 38, 88)    # índigo apagado

# ── Paleta de chips por proyecto (color-coded, se elige por hash estable) ────
CHIP_COLORS = [
    "#818cf8",  # índigo
    "#a78bfa",  # violeta
    "#34d399",  # esmeralda
    "#fbbf24",  # ámbar
    "#f472b6",  # rosa
    "#38bdf8",  # cielo
    "#2dd4bf",  # turquesa
    "#fb923c",  # naranja
    "#a3e635",  # lima
    "#f87171",  # coral
]


# ══════════════════════════════════════════════════════════════════════════════
#  TIPOGRAFÍA
# ══════════════════════════════════════════════════════════════════════════════

FONT_UI   = "Segoe UI"     # interfaz general
FONT_MONO = "Consolas"     # rutas, código, preview de bloques


def font(size=10, weight="normal", *, family=FONT_UI):
    """Atajo para construir tuplas de fuente tkinter."""
    return (family, size, weight)


def mono(size=10, weight="normal"):
    return (FONT_MONO, size, weight)


# ══════════════════════════════════════════════════════════════════════════════
#  ESTILOS ttk (solo scrollbars — el resto de la UI es tk puro y custom)
# ══════════════════════════════════════════════════════════════════════════════

def init_ttk_styles(root):
    """Configura el tema 'clam' y las scrollbars glass casi invisibles."""
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except Exception:
        pass

    style.configure(
        "Glass.Vertical.TScrollbar",
        background=BORDER, troughcolor=BG_DEEP, bordercolor=BG_DEEP,
        arrowcolor=TEXT_DIM, relief="flat", width=10, borderwidth=0,
    )
    style.map("Glass.Vertical.TScrollbar", background=[("active", TEXT_DIM)])
    return style


# ══════════════════════════════════════════════════════════════════════════════
#  ICONO EMBEBIDO (ICO multi-resolución en base64)
#  Parte de la identidad visual → vive aquí. utils.extract_icon() lo materializa.
# ══════════════════════════════════════════════════════════════════════════════

ICON_B64 = "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"
