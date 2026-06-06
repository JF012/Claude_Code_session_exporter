"""
ui/sidebar.py — Sidebar izquierdo: marca + lista de proyectos.

Muestra el logo ⬡ con un glow índigo, la sección "Proyectos" con "Todas las
sesiones" al inicio (seleccionada por defecto) y una fila por proyecto con su
chip de color, nombre y badge de cantidad. Abajo, un botón para recargar.

Comunica la selección hacia arriba con `on_select(project | None)`, donde None
representa "Todas las sesiones".
"""
import tkinter as tk

import styles as S
from core.utils import lerp_rgb, rgb_hex
from widgets import make_badge, ScrollableFrame, RoundedButton

WIDTH = 248


class _NavRow(tk.Frame):
    """Fila clicable del sidebar (Todas las sesiones / un proyecto)."""
    def __init__(self, parent, *, icon, label, count, fg_dot, on_click):
        super().__init__(parent, bg=S.BG_PANEL, cursor="hand2")
        self._on_click = on_click
        self._selected = False

        # Barra de acento a la izquierda (se enciende al seleccionar)
        self._bar = tk.Frame(self, bg=S.BG_PANEL, width=3)
        self._bar.pack(side="left", fill="y")

        self._inner = tk.Frame(self, bg=S.BG_PANEL)
        self._inner.pack(side="left", fill="both", expand=True, padx=(10, 11), pady=9)

        self._icon = tk.Label(self._inner, text=icon, bg=S.BG_PANEL, fg=fg_dot,
                              font=S.font(10))
        self._icon.pack(side="left", padx=(0, 8))
        self._label = tk.Label(self._inner, text=label, bg=S.BG_PANEL, fg=S.TEXT_MUTE,
                               font=S.font(10), anchor="w")
        self._label.pack(side="left", fill="x", expand=True)
        self._badge = make_badge(self._inner, count, fg=S.TEXT_DIM, bg=S.BG_ELEV)
        self._badge.pack(side="right")

        self._parts = [self, self._inner, self._icon, self._label]
        for w in self._parts:
            w.bind("<Enter>", self._on_enter)
            w.bind("<Leave>", self._on_leave)
            w.bind("<Button-1>", lambda e: self._on_click())

    def _paint(self, bg, label_fg, bar):
        for w in (self, self._inner, self._icon, self._label):
            w.config(bg=bg)
        self._label.config(fg=label_fg)
        self._icon.config(bg=bg)
        self._bar.config(bg=bar)

    def _on_enter(self, _):
        if not self._selected:
            self._paint(S.ROW_HOVER, S.TEXT, S.BORDER)

    def _on_leave(self, _):
        if not self._selected:
            self._paint(S.BG_PANEL, S.TEXT_MUTE, S.BG_PANEL)

    def set_selected(self, on: bool):
        self._selected = on
        if on:
            self._paint(S.ROW_SEL, S.TEXT, S.ACCENT)
        else:
            self._paint(S.BG_PANEL, S.TEXT_MUTE, S.BG_PANEL)


class Sidebar(tk.Frame):
    def __init__(self, parent, *, on_select, on_reload):
        super().__init__(parent, bg=S.BG_PANEL, width=WIDTH)
        self.pack_propagate(False)
        self._on_select = on_select
        self._on_reload = on_reload
        self._rows = []          # _NavRow list (índice 0 = "Todas las sesiones")
        self._selected_index = 0

        self._build_brand()
        tk.Frame(self, bg=S.BORDER_SOFT, height=1).pack(fill="x", padx=16)

        # Encabezado de sección
        head = tk.Frame(self, bg=S.BG_PANEL)
        head.pack(fill="x", padx=20, pady=(18, 8))
        tk.Label(head, text="PROJECTS", bg=S.BG_PANEL, fg=S.TEXT_DIM,
                 font=S.font(8, "bold")).pack(side="left")
        self._proj_count = tk.Label(head, text="", bg=S.BG_PANEL, fg=S.TEXT_FAINT,
                                    font=S.font(8, "bold"))
        self._proj_count.pack(side="right")

        # Lista scrollable de filas
        self._list = ScrollableFrame(self, bg=S.BG_PANEL)
        self._list.pack(fill="both", expand=True, padx=(8, 6))

        # Pie: recargar
        tk.Frame(self, bg=S.BORDER_SOFT, height=1).pack(fill="x", padx=16)
        foot = tk.Frame(self, bg=S.BG_PANEL)
        foot.pack(fill="x", padx=14, pady=14)
        RoundedButton(foot, "↻  Refresh sessions", self._on_reload,
                      variant="flat", font_size=9).pack(fill="x")

    # ── Marca (logo + glow) ───────────────────────────────────────────────────
    def _build_brand(self):
        wrap = tk.Frame(self, bg=S.BG_PANEL)
        wrap.pack(fill="x", pady=(0, 4))

        glow = tk.Canvas(wrap, height=66, highlightthickness=0, bd=0, bg=S.BG_PANEL)
        glow.pack(fill="x")
        glow.bind("<Configure>", lambda e: self._draw_glow(glow))

        glow.create_text(22, 34, text="⬡", font=S.font(20), fill=S.ACCENT,
                         anchor="w", tags="brand")
        glow.create_text(52, 27, text="Claude Exporter", font=S.font(13, "bold"),
                         fill=S.TEXT, anchor="w", tags="brand")
        glow.create_text(53, 44, text="Session → Markdown", font=S.font(8),
                         fill=S.TEXT_DIM, anchor="w", tags="brand")
        self._glow = glow

    def _draw_glow(self, c):
        c.delete("glow")
        w, h = c.winfo_width(), c.winfo_height()
        if w <= 1 or h <= 1:
            return
        step = 4
        for y in range(0, h, step):
            t = y / max(h - 1, 1)
            r, g, b = lerp_rgb(S.GLOW_BOT_RGB, S.GLOW_TOP_RGB, t)
            c.create_rectangle(0, y, w, y + step, fill=rgb_hex(r, g, b),
                               outline="", tags="glow")
        c.tag_lower("glow")
        c.tag_raise("brand")

    # ── Población ─────────────────────────────────────────────────────────────
    def set_projects(self, projects, total_sessions):
        """Reconstruye la lista: 'Todas las sesiones' + una fila por proyecto."""
        self._list.clear()
        self._rows = []
        self._proj_count.config(text=str(len(projects)))

        all_row = _NavRow(self._list.body, icon="◆", label="All sessions",
                          count=total_sessions, fg_dot=S.ACCENT_SOFT,
                          on_click=lambda: self._select(0))
        all_row.pack(fill="x", pady=1)
        self._rows.append(all_row)

        for i, p in enumerate(projects, start=1):
            fg, _ = p.chip_colors
            row = _NavRow(self._list.body, icon="▣", label=p.name, count=p.count,
                          fg_dot=fg, on_click=lambda idx=i: self._select(idx))
            row.pack(fill="x", pady=1)
            self._rows.append(row)

        self._projects = projects
        self._selected_index = min(self._selected_index, len(self._rows) - 1)
        self._refresh_selection()
        self._list.scroll_to_top()

    def _select(self, index):
        self._selected_index = index
        self._refresh_selection()
        self._on_select(None if index == 0 else self._projects[index - 1])

    def _refresh_selection(self):
        for i, row in enumerate(self._rows):
            row.set_selected(i == self._selected_index)

    def reset_to_all(self):
        self._selected_index = 0
        self._refresh_selection()
