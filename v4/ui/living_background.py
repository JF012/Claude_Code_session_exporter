"""
ui/living_background.py — Fondo "vivo" del área principal.

Un lienzo que respira: un gradiente índigo muy sutil sobre el que derivan
varios orbes de glow con movimiento lento (tipo lissajous). Todo es geometría
de tkinter (sin imágenes ni dependencias externas).

Se coloca DETRÁS del contenido del área central y sólo asoma por los márgenes
—nunca sobre la tabla ni los paneles—, así que aporta vida sin restar
legibilidad. La paleta vive en `styles.py` (LIVE_GRAD_* / LIVE_ORBS).
"""
import math
import tkinter as tk

import styles as S
from core.utils import mix

ORB_LAYERS  = 16     # óvalos concéntricos por orbe (cuantos más, más suave el glow)
FPS_MS      = 33     # ~30 fps; el movimiento ya es lento de por sí
RECOLOR_EVERY = 6    # recolorea cada N frames (el color cambia despacio)


class _Orb:
    """Un orbe de glow: ancla relativa + deriva sinusoidal en X e Y."""
    def __init__(self, color, peak, ax, ay, rx, ry, sx, sy, px, py, radius):
        self.color = color          # color base del glow
        self.peak = peak            # intensidad pico (0..1) hacia el centro
        self.ax, self.ay = ax, ay   # ancla relativa al tamaño (0..1)
        self.rx, self.ry = rx, ry   # amplitud de deriva (px)
        self.sx, self.sy = sx, sy   # velocidad angular (rad/s)
        self.px, self.py = px, py   # desfase inicial
        self.radius = radius        # radio del glow (px)
        self.ids = []               # óvalos, de fuera (i=0) hacia dentro

    def center(self, t, w, h):
        cx = self.ax * w + self.rx * math.sin(self.sx * t + self.px)
        cy = self.ay * h + self.ry * math.sin(self.sy * t + self.py)
        return cx, cy


class LivingBackground(tk.Canvas):
    """Canvas animado para usar como capa de fondo (place + lower)."""
    def __init__(self, parent):
        super().__init__(parent, highlightthickness=0, bd=0,
                         bg=S.LIVE_GRAD_BOT, takefocus=0)
        # OJO: no usar self._w / self._h → tkinter reserva self._w para la ruta
        # interna del widget. Guardamos el tamaño en _cw / _ch.
        self._cw = self._ch = 0
        self._t = 0.0
        self._frame = 0
        self._running = False
        self._after = None
        self._orbs = self._make_orbs()
        self.bind("<Configure>", self._on_configure)
        self.bind("<Destroy>", lambda e: self._stop())

    # ── Orbes (parámetros fijos → estable entre ejecuciones) ──────────────────
    def _make_orbs(self):
        # ax,   ay,   rx, ry, sx,    sy,    px,  py,  radio
        specs = [
            (0.16, 0.18, 74, 48, 0.055, 0.041, 0.0, 1.7, 158),
            (0.84, 0.26, 66, 54, 0.043, 0.060, 2.1, 0.6, 138),
            (0.30, 0.80, 84, 60, 0.038, 0.050, 4.0, 2.4, 172),
            (0.74, 0.72, 58, 66, 0.061, 0.037, 1.1, 3.3, 146),
            (0.50, 0.48, 96, 44, 0.034, 0.047, 5.2, 1.2, 128),
        ]
        return [_Orb(color, peak, *s) for (color, peak), s in zip(S.LIVE_ORBS, specs)]

    # ── Resize: redibuja gradiente y reconstruye los óvalos ───────────────────
    def _on_configure(self, e):
        self._cw, self._ch = e.width, e.height
        self._draw_gradient()
        self._build_orbs()
        if not self._running:
            self._start()

    def _grad_color(self, y):
        t = y / max(self._ch - 1, 1)
        return mix(S.LIVE_GRAD_TOP, S.LIVE_GRAD_BOT, t)

    def _draw_gradient(self):
        self.delete("grad")
        if self._cw <= 1 or self._ch <= 1:
            return
        step = 6
        for y in range(0, self._ch, step):
            self.create_rectangle(0, y, self._cw, y + step, outline="",
                                  fill=self._grad_color(y), tags="grad")
        self.tag_lower("grad")

    def _build_orbs(self):
        self.delete("orb")
        for orb in self._orbs:
            orb.ids = [self.create_oval(0, 0, 0, 0, outline="", tags="orb")
                       for _ in range(ORB_LAYERS)]
        self.tag_raise("orb")
        self._render(recolor=True)

    # ── Render de un frame ────────────────────────────────────────────────────
    def _render(self, recolor=False):
        w, h = self._cw, self._ch
        if w <= 1 or h <= 1:
            return
        for orb in self._orbs:
            cx, cy = orb.center(self._t, w, h)
            base_bg = self._grad_color(cy) if recolor else None
            R = orb.radius
            for i, oid in enumerate(orb.ids):
                frac = i / (ORB_LAYERS - 1)        # 0 fuera → 1 dentro
                r = R * (1.0 - frac * 0.94)
                self.coords(oid, cx - r, cy - r, cx + r, cy + r)
                if recolor:
                    # intensidad creciente hacia el centro (perfil suave)
                    inten = orb.peak * (frac ** 1.6)
                    self.itemconfig(oid, fill=mix(base_bg, orb.color, inten))

    # ── Bucle de animación ────────────────────────────────────────────────────
    def _start(self):
        self._running = True
        self._tick()

    def _stop(self):
        self._running = False
        if self._after is not None:
            try:
                self.after_cancel(self._after)
            except Exception:
                pass
            self._after = None

    def _tick(self):
        if not self._running:
            return
        try:
            visible = self.winfo_viewable()
        except Exception:
            visible = True
        if visible:
            self._t += FPS_MS / 1000.0
            self._frame += 1
            self._render(recolor=(self._frame % RECOLOR_EVERY == 0))
        self._after = self.after(FPS_MS, self._tick)
