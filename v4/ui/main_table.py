"""
ui/main_table.py — Área central: buscador + lista de sesiones.

La "tabla" no es un ttk.Treeview sino una lista de filas custom (SessionRow),
porque el diseño pide cosas que el Treeview no permite: un chip de color por
proyecto, una celda de dos líneas (título + preview) y un badge numérico.

Cada fila se pinta con zebra striping sutil y reacciona a hover y selección con
un glow índigo. El texto se trunca al ancho disponible (elipsis real) y se
recalcula cuando la ventana cambia de tamaño.
"""
import tkinter as tk
import tkinter.font as tkfont

import styles as S
from core.utils import format_ts
from widgets import (FocusField, ScrollableFrame, make_chip, make_badge,
                     Tooltip, rounded_card_image, bevel_divider, HAS_PIL)
from ui.living_background import LivingBackground

# Anchos fijos (px) de las columnas no elásticas; la sesión ocupa el resto.
# Ajustados a su contenido real ("2026-06-06 07:55" ≈ 90 px, badge ≈ 34 px)
# para ceder el máximo de ancho a la columna de sesión (título + preview).
COL_DATE = 104
COL_PROJ = 140
COL_MSGS = 50
ROW_H    = 62
MAX_ROWS = 400          # tope defensivo para no renderizar miles de filas

# Tarjeta de contenido: el contorno redondeado se dibuja como imagen RGBA sobre
# el canvas del fondo vivo; el Frame real (cuadrado) vive INSET px dentro del
# contorno para que sus esquinas rectas queden siempre bajo el vidrio.
# INSET debe ser ≥ 0.3·RADIUS_CARD para que la esquina recta no asome del arco.
CARD_INSET  = 7
CARD_SHADOW = 14        # aire transparente alrededor (donde respira la sombra)


def _truncate(text, font: tkfont.Font, max_px: int) -> str:
    """Recorta `text` con elipsis para que quepa en `max_px` (búsqueda binaria)."""
    text = (text or "").replace("\n", " ").strip()
    if max_px <= 0 or not text:
        return text
    if font.measure(text) <= max_px:
        return text
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if font.measure(text[:mid] + "…") <= max_px:
            lo = mid
        else:
            hi = mid - 1
    return text[:lo].rstrip() + "…"


class SessionRow(tk.Frame):
    """Una fila de sesión: fecha · chip proyecto · título+preview · badge msgs."""
    def __init__(self, parent, session, index, *, on_select, on_activate, fonts):
        self.session = session
        self._index = index
        self._base_bg = S.ROW_EVEN if index % 2 == 0 else S.ROW_ODD
        self._selected = False
        self._on_select = on_select
        self._on_activate = on_activate
        self._f_title, self._f_prev = fonts

        super().__init__(parent, bg=self._base_bg, height=ROW_H, cursor="hand2")
        self.pack_propagate(False)

        # Barra de acento: gris apagado en reposo → índigo en hover/selección.
        # Es el feedback principal de la fila (el fondo apenas cambia).
        self._bar = tk.Frame(self, bg=S.ROW_BAR, width=3)
        self._bar.pack(side="left", fill="y")

        inner = tk.Frame(self, bg=self._base_bg)
        inner.pack(side="left", fill="both", expand=True, padx=(13, 14))
        self._inner = inner

        # Fecha (izquierda, fija)
        dcell = tk.Frame(inner, bg=self._base_bg, width=COL_DATE)
        dcell.pack(side="left", fill="y")
        dcell.pack_propagate(False)
        self._date = tk.Label(dcell, text=format_ts(session.last_ts), bg=self._base_bg,
                              fg=S.TEXT_DIM, font=S.font(9), anchor="w")
        self._date.pack(side="left", fill="y", expand=True)

        # Proyecto (chip de color, fijo)
        pcell = tk.Frame(inner, bg=self._base_bg, width=COL_PROJ)
        pcell.pack(side="left", fill="y")
        pcell.pack_propagate(False)
        fg, bg = session.chip_colors
        proj_txt = _truncate(session.project, tkfont.Font(family=S.FONT_UI, size=8, weight="bold"), COL_PROJ - 24)
        self._chip = make_chip(pcell, proj_txt, fg, bg)
        self._chip.pack(side="left", anchor="center", pady=2)

        # Mensajes (badge, derecha, fijo)
        mcell = tk.Frame(inner, bg=self._base_bg, width=COL_MSGS)
        mcell.pack(side="right", fill="y")
        mcell.pack_propagate(False)
        self._badge = make_badge(mcell, session.message_count, fg=S.ACCENT_SOFT,
                                 bg=S.BG_ELEV)
        self._badge.pack(side="right", anchor="center")

        # Sesión (título + preview, elástica) — se rellena en set_width()
        scell = tk.Frame(inner, bg=self._base_bg)
        scell.pack(side="left", fill="both", expand=True, padx=(2, 10))
        self._scell = scell
        self._title = tk.Label(scell, text="", bg=self._base_bg, fg=S.TEXT,
                               font=S.semi(10), anchor="w")
        self._title.pack(fill="x", anchor="w", pady=(11, 0))
        self._preview = tk.Label(scell, text="", bg=self._base_bg, fg=S.TEXT_DIM,
                                 font=S.font(9), anchor="w")
        self._preview.pack(fill="x", anchor="w")
        self._last_w = 0

        # Eventos (hay que enlazar también los hijos, que capturan el ratón)
        self._parts = [self, inner, dcell, self._date, pcell, mcell,
                       scell, self._title, self._preview]
        for w in self._parts:
            w.bind("<Enter>", self._on_enter)
            w.bind("<Leave>", self._on_leave)
            w.bind("<Button-1>", lambda e: self._on_select(self))
            w.bind("<Double-1>", lambda e: self._on_activate(self.session))

        Tooltip(self, lambda: self.session.project_full or self.session.project)

    # ── Truncado dependiente del ancho ────────────────────────────────────────
    def set_width(self, total_px: int):
        avail = total_px - 3 - 27 - COL_DATE - COL_PROJ - COL_MSGS - 12
        if avail < 80:
            avail = 80
        if abs(avail - self._last_w) < 6:
            return
        self._last_w = avail
        self._title.config(text=_truncate(self.session.display_name, self._f_title, avail))
        prev = self.session.first_user_msg if self.session.title else ""
        self._preview.config(text=_truncate(prev, self._f_prev, avail))

    # ── Pintado de estados ────────────────────────────────────────────────────
    def _paint(self, bg, bar, title_fg, prev_fg, date_fg):
        for w in (self, self._inner, self._date.master, self._date,
                  self._chip.master, self._badge.master, self._scell,
                  self._title, self._preview):
            w.config(bg=bg)
        self._bar.config(bg=bar)
        self._title.config(fg=title_fg)
        self._preview.config(fg=prev_fg)
        self._date.config(fg=date_fg)

    def _on_enter(self, _):
        if not self._selected:
            self._paint(S.ROW_HOVER, S.ACCENT_SOFT, S.TEXT, S.TEXT_MUTE, S.TEXT_MUTE)

    def _on_leave(self, _):
        if not self._selected:
            self._paint(self._base_bg, S.ROW_BAR, S.TEXT, S.TEXT_DIM, S.TEXT_DIM)

    def set_selected(self, on: bool):
        self._selected = on
        if on:
            self._paint(S.ROW_SEL, S.ACCENT, S.SEL_TEXT, S.TEXT_MUTE, S.TEXT_MUTE)
        else:
            self._paint(self._base_bg, S.ROW_BAR, S.TEXT, S.TEXT_DIM, S.TEXT_DIM)


class _SkeletonRow(tk.Frame):
    """Fila fantasma para el estado de carga: bloques BG_ELEV estáticos con la
    misma geometría que SessionRow. La lista nunca se ve vacía mientras el hilo
    escanea, así la apertura se percibe instantánea. Cero animación, cero coste."""
    def __init__(self, parent, index):
        base = S.ROW_EVEN if index % 2 == 0 else S.ROW_ODD
        super().__init__(parent, bg=base, height=ROW_H)
        self.pack_propagate(False)
        tk.Frame(self, bg=S.ROW_BAR, width=3).pack(side="left", fill="y")
        inner = tk.Frame(self, bg=base)
        inner.pack(side="left", fill="both", expand=True, padx=(13, 14))

        def cell(width):
            c = tk.Frame(inner, bg=base, width=width)
            c.pack(side="left", fill="y")
            c.pack_propagate(False)
            return c

        # Fecha · chip de proyecto · badge (anchos reales de las columnas)
        tk.Frame(cell(COL_DATE), bg=S.BG_ELEV, width=72, height=9).pack(side="left")
        tk.Frame(cell(COL_PROJ), bg=S.BG_ELEV, width=92, height=18).pack(side="left")
        mcell = tk.Frame(inner, bg=base, width=COL_MSGS)
        mcell.pack(side="right", fill="y")
        mcell.pack_propagate(False)
        tk.Frame(mcell, bg=S.BG_ELEV, width=30, height=16).pack(side="right")

        # Sesión: título ancho + preview más corto (elásticos, como la real)
        scell = tk.Frame(inner, bg=base)
        scell.pack(side="left", fill="both", expand=True, padx=(2, 10))
        tk.Frame(scell, bg=S.BG_ELEV, height=10).pack(fill="x", padx=(0, 70),
                                                      pady=(16, 7))
        tk.Frame(scell, bg=S.BG_ELEV, height=8).pack(fill="x", padx=(0, 150))


class MainTable(tk.Frame):
    def __init__(self, parent, *, on_select, on_activate, on_search, on_sort=None):
        super().__init__(parent, bg=S.BG_DEEP)
        self._on_select = on_select
        self._on_activate = on_activate
        self._on_search = on_search
        self._on_sort = on_sort
        self._rows = []
        self._selected_row = None
        self._search_after = None
        self._resize_after = None
        self._headers = {}          # sort_key → (label, base_text)
        self._active_sort = "last_ts"

        # Fuentes de medición (compartidas por todas las filas; la del título
        # debe coincidir con S.semi(10) o el truncado quedaría corto/largo)
        self._f_title = tkfont.Font(font=S.semi(10))
        self._f_prev  = tkfont.Font(family=S.FONT_UI, size=9)

        # ── Fondo vivo (capa inferior; asoma sólo por los márgenes) ───────────
        # Se crea antes que el resto de hijos → queda al fondo del apilado.
        # (En un Canvas, .lower() baja un item, no el widget: usamos Misc.lower.)
        self._bg = LivingBackground(self)
        self._bg.place(x=0, y=0, relwidth=1, relheight=1)
        tk.Misc.lower(self._bg)

        # ── Buscador glass (flota sobre la zona hero del fondo vivo) ──────────
        # Mismo radio que los botones y borde visual alineado con la tarjeta
        # (padx 14 + 8 px de margen interno de la imagen = 22 px de margen real).
        self._search = FocusField(self, icon="🔍",
                                  placeholder="Search by session, project or date…",
                                  font=S.font(11), surface=S.HERO_SURFACE,
                                  radius=S.RADIUS_CTRL, shadow=False)
        self._search.pack(fill="x", padx=14, pady=(30, 14))
        self._search.var.trace_add("write", lambda *_: self._debounce_search())

        # ── Tarjeta de contenido (panel elevado que flota sobre el fondo vivo) ─
        # Unifica título + columnas + lista en una sola superficie elevada. Con
        # Pillow, su contorno redondeado (sombra + bisel + borde) se dibuja como
        # overlay RGBA sobre el canvas del fondo y este Frame queda CARD_INSET px
        # dentro; el borde visible cae así a 22 px, alineado con el buscador.
        card = tk.Frame(self, bg=S.BG_CARD)
        card.pack(fill="both", expand=True, padx=22 + CARD_INSET,
                  pady=(2 + CARD_INSET, 12 + CARD_INSET))
        self._card = card
        self._card_item = None      # item de imagen del overlay (canvas del fondo)
        self._card_photo = None     # ref viva de la PhotoImage (anti-GC)
        self._card_after = None
        if HAS_PIL:
            card.bind("<Configure>", self._on_card_configure)
        else:
            # Fallback plano: bisel superior de 1 px, como hasta ahora.
            tk.Frame(card, bg=S.CARD_HILITE, height=1).pack(fill="x")

        # Título + contador
        head = tk.Frame(card, bg=S.BG_CARD)
        head.pack(fill="x", padx=13, pady=(9, 10))
        tk.Label(head, text="Recent sessions", bg=S.BG_CARD, fg=S.TEXT,
                 font=S.font(12, "bold")).pack(side="left")
        self._count = make_badge(head, "0", fg=S.ACCENT_SOFT, bg=S.BG_ELEV, font_size=9)
        self._count.pack(side="left", padx=10)

        # Cabecera de columnas (clic = ordenar)
        hdr = tk.Frame(card, bg=S.BG_CARD)
        hdr.pack(fill="x", padx=(13, 13))
        self._col_header(hdr, "LAST ACTIVITY", width=COL_DATE + 16, anchor="w",
                         sort_key="last_ts")
        self._col_header(hdr, "PROJECT", width=COL_PROJ, anchor="w",
                         sort_key="project")
        self._col_header(hdr, "MSGS", width=COL_MSGS, anchor="e", side="right",
                         sort_key="message_count")
        self._col_header(hdr, "SESSION", width=0, anchor="w", expand=True,
                         sort_key="display_name")
        bevel_divider(card, bg=S.BG_CARD, padx=13, pady=(6, 0))

        # Lista
        self._list = ScrollableFrame(card, bg=S.BG_CARD)
        self._list.pack(fill="both", expand=True, padx=(8, 4), pady=(2, 4))
        self._list.canvas.bind("<Configure>", self._on_canvas_resize, add="+")

        # Estado vacío (se construye bajo demanda en set_sessions)
        self._empty = None

    def _col_header(self, parent, text, *, width, anchor, expand=False,
                    side="left", sort_key=None):
        cell = tk.Frame(parent, bg=S.BG_CARD, width=width)
        cell.pack(side=side, fill="x" if expand else "y", expand=expand)
        if width:
            cell.pack_propagate(False)
        lbl = tk.Label(cell, text=text, bg=S.BG_CARD, fg=S.TEXT_FAINT,
                       font=S.font(8, "bold"), anchor=anchor)
        lbl.pack(side="left", fill="x", expand=True, pady=(0, 6))
        if sort_key and self._on_sort:
            self._headers[sort_key] = (lbl, text)
            lbl.config(cursor="hand2")
            lbl.bind("<Button-1>", lambda e, k=sort_key: self._on_sort(k))
            lbl.bind("<Enter>", lambda e, w=lbl: w.config(fg=S.TEXT_MUTE))
            lbl.bind("<Leave>", lambda e, w=lbl: self._restore_header(w))

    def _restore_header(self, lbl):
        # No atenúes la columna activa al salir el ratón
        for key, (w, _) in self._headers.items():
            if w is lbl:
                lbl.config(fg=S.ACCENT_SOFT if key == self._active_sort else S.TEXT_FAINT)
                return

    def set_sort_indicator(self, key, rev):
        """Resalta la columna activa y añade la flecha de dirección."""
        self._active_sort = key
        arrow = " ▾" if rev else " ▴"
        for k, (lbl, base) in self._headers.items():
            if k == key:
                lbl.config(text=base + arrow, fg=S.ACCENT_SOFT)
            else:
                lbl.config(text=base, fg=S.TEXT_FAINT)

    # ── Overlay de la tarjeta (contorno redondeado sobre el fondo vivo) ───────
    def _on_card_configure(self, _):
        if self._card_after:
            self.after_cancel(self._card_after)
        self._card_after = self.after(90, self._draw_card_overlay)

    def _draw_card_overlay(self):
        """Redibuja la imagen RGBA del contorno (sombra + bisel + borde) en el
        canvas del fondo, ajustada a la posición/tamaño actual del Frame. Sólo
        corre al cambiar la geometría (debounced) → coste cero por fotograma."""
        self._card_after = None
        x, y = self._card.winfo_x(), self._card.winfo_y()
        w, h = self._card.winfo_width(), self._card.winfo_height()
        if w <= 1 or h <= 1:
            return
        pad = CARD_INSET + CARD_SHADOW
        self._card_photo = rounded_card_image(
            w + 2 * pad, h + 2 * pad, radius=S.RADIUS_CARD, margin=CARD_SHADOW)
        if self._card_item is None:
            self._card_item = self._bg.create_image(x - pad, y - pad, anchor="nw",
                                                    image=self._card_photo)
        else:
            self._bg.coords(self._card_item, x - pad, y - pad)
            self._bg.itemconfig(self._card_item, image=self._card_photo)

    # ── Búsqueda (debounced) ──────────────────────────────────────────────────
    def _debounce_search(self):
        if self._search_after:
            self.after_cancel(self._search_after)
        self._search_after = self.after(170, lambda: self._on_search(self._search.value))

    # ── Resize (re-trunca el texto de las filas, debounced) ───────────────────
    def _on_canvas_resize(self, event):
        if self._resize_after:
            self.after_cancel(self._resize_after)
        self._resize_after = self.after(110, lambda w=event.width: self._apply_width(w))

    def _apply_width(self, width):
        for row in self._rows:
            row.set_width(width)

    # ── Estado de carga (skeleton) ────────────────────────────────────────────
    def show_skeleton(self, count=4):
        """Filas fantasma mientras el hilo escanea: la lista nunca se ve vacía
        y la apertura/recarga se percibe instantánea."""
        self._list.clear()
        self._rows = []
        self._selected_row = None
        self._empty = None
        for i in range(count):
            _SkeletonRow(self._list.body, i).pack(fill="x")

    # ── Estado vacío (icono minimalista dibujado en Canvas) ───────────────────
    @staticmethod
    def _round_rect(c, x0, y0, x1, y1, r, *, outline, fill=None, width=2):
        """Rectángulo redondeado en un Canvas: relleno (2 rects + 4 óvalos) y/o
        contorno (4 arcos + 4 líneas). Geometría tk pura, sin imágenes."""
        if fill is not None:
            c.create_rectangle(x0 + r, y0, x1 - r, y1, fill=fill, outline="")
            c.create_rectangle(x0, y0 + r, x1, y1 - r, fill=fill, outline="")
            for (cx, cy) in ((x0, y0), (x1 - 2 * r, y0), (x0, y1 - 2 * r),
                             (x1 - 2 * r, y1 - 2 * r)):
                c.create_oval(cx, cy, cx + 2 * r, cy + 2 * r, fill=fill, outline="")
        if outline:
            for (ax, ay, start) in ((x0, y0, 90), (x1 - 2 * r, y0, 0),
                                    (x0, y1 - 2 * r, 180), (x1 - 2 * r, y1 - 2 * r, 270)):
                c.create_arc(ax, ay, ax + 2 * r, ay + 2 * r, start=start, extent=90,
                             style="arc", outline=outline, width=width)
            c.create_line(x0 + r, y0, x1 - r, y0, fill=outline, width=width)
            c.create_line(x0 + r, y1, x1 - r, y1, fill=outline, width=width)
            c.create_line(x0, y0 + r, x0, y1 - r, fill=outline, width=width)
            c.create_line(x1, y0 + r, x1, y1 - r, fill=outline, width=width)

    def _build_empty_state(self):
        """Pila de documentos minimalista (TEXT_FAINT) + mensaje."""
        box = tk.Frame(self._list.body, bg=S.BG_CARD)
        icon = tk.Canvas(box, width=88, height=80, bg=S.BG_CARD,
                         highlightthickness=0, bd=0)
        icon.pack()
        # Hoja trasera (asoma por detrás) + hoja frontal rellena que la tapa
        self._round_rect(icon, 30, 6, 74, 56, 7, outline=S.TEXT_FAINT)
        self._round_rect(icon, 16, 18, 60, 72, 7, outline=S.TEXT_FAINT,
                         fill=S.BG_CARD)
        for i, x1 in enumerate((48, 48, 38)):     # líneas de "texto"
            y = 32 + i * 11
            icon.create_line(26, y, x1, y, fill=S.TEXT_FAINT, width=2)
        tk.Label(box, text="No sessions found", bg=S.BG_CARD, fg=S.TEXT_MUTE,
                 font=S.semi(11)).pack(pady=(14, 3))
        tk.Label(box, text="Try a different search term or refresh.",
                 bg=S.BG_CARD, fg=S.TEXT_DIM, font=S.font(9)).pack()
        return box

    # ── Población ─────────────────────────────────────────────────────────────
    def set_sessions(self, sessions, *, subtitle_total=None):
        self._list.clear()
        self._rows = []
        self._selected_row = None
        total = subtitle_total if subtitle_total is not None else len(sessions)
        self._count.config(text=f"{len(sessions)}" if len(sessions) == total
                           else f"{len(sessions)} / {total}")

        if not sessions:
            self._empty = self._build_empty_state()
            self._empty.pack(pady=52)
            return

        shown = sessions[:MAX_ROWS]
        for i, s in enumerate(shown):
            row = SessionRow(self._list.body, s, i,
                             on_select=self._select_row,
                             on_activate=self._on_activate,
                             fonts=(self._f_title, self._f_prev))
            row.pack(fill="x")
            self._rows.append(row)

        if len(sessions) > MAX_ROWS:
            tk.Label(self._list.body,
                     text=f"… and {len(sessions) - MAX_ROWS} more (refine your search)",
                     bg=S.BG_CARD, fg=S.TEXT_DIM, font=S.font(9)).pack(pady=12)

        self._list.scroll_to_top()
        # Truncar al ancho actual del canvas
        self.after_idle(lambda: self._apply_width(self._list.canvas.winfo_width()))

    def _select_row(self, row: SessionRow):
        if self._selected_row is row:
            return
        if self._selected_row is not None:
            self._selected_row.set_selected(False)
        self._selected_row = row
        row.set_selected(True)
        self._on_select(row.session)

    def clear_selection(self):
        if self._selected_row is not None:
            self._selected_row.set_selected(False)
            self._selected_row = None

    def focus_search(self):
        self._search.entry.focus_set()
