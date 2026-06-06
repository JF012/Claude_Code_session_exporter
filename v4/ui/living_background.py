"""
ui/living_background.py — Fondo "vivo" del área principal.

Un lienzo glassmorphism que respira: un gradiente índigo sobre el que derivan
varios orbes de glow suave (deriva tipo lissajous). Geometría pura de tkinter,
sin imágenes ni dependencias externas.

Rendimiento (clave para ir fluido a ~60 fps):
  Cada orbe se construye UNA sola vez como una pila de óvalos concéntricos con
  color FIJO (el glow se premezcla contra el fondo en su ancla). La animación NO
  recolorea ni reposiciona óvalo por óvalo: traslada el orbe entero con
  `Canvas.move(tag, dx, dy)` —una sola llamada Tcl por orbe y frame—. Así el
  coste por frame es ínfimo y se puede subir el nº de capas (blur más suave) y la
  opacidad sin penalizar los fps. La paleta vive en `styles.py`.

Se coloca DETRÁS del contenido del área central y asoma por la banda hero (sobre
el buscador) y los márgenes, aportando vida sin restar legibilidad a la tabla.
"""
import math
import tkinter as tk

import styles as S
from core.utils import mix

ORB_LAYERS = 30      # óvalos concéntricos por orbe → glow muy suave (coste sólo al construir)
FPS_MS     = 16      # ~60 fps
GRAD_STEP  = 4       # alto (px) de cada banda del gradiente
GRAD_OVER  = 28      # sobredibujo vertical del gradiente para desplazarlo sin huecos
GRAD_AMP   = 16      # amplitud de la deriva vertical del gradiente (px)
GRAD_SPD   = 0.16    # velocidad de esa deriva (rad/s) → ~39 s por ciclo


class _Orb:
    """Orbe de glow elíptico: ancla relativa + deriva sinusoidal lenta en X/Y.

    Es elíptico (rw≠rh) para poder cubrir la banda hero con una sola elipse
    ancha y evitar el "mordisco" oscuro que produciría solapar varios círculos
    opacos.
    """
    def __init__(self, color, peak, ax, ay, dx, dy, sx, sy, px, py, rw, rh):
        self.color = color          # color del glow (paleta índigo/violeta)
        self.peak = peak            # intensidad pico (0..1) hacia el centro
        self.ax, self.ay = ax, ay   # ancla relativa al tamaño (0..1)
        self.dx, self.dy = dx, dy   # amplitud de deriva (px)
        self.sx, self.sy = sx, sy   # velocidad angular (rad/s)
        self.px, self.py = px, py   # desfase inicial
        self.rw, self.rh = rw, rh   # radios del glow (px)
        self.tag = None             # tag Tcl propio → se mueve en bloque
        self.cx = self.cy = 0.0     # centro actual (px); se trackea para mover por delta

    def target(self, t, w, h):
        cx = self.ax * w + self.dx * math.sin(self.sx * t + self.px)
        cy = self.ay * h + self.dy * math.sin(self.sy * t + self.py)
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
        self._grad_dy = 0.0          # desplazamiento vertical actual del gradiente
        self._running = False
        self._after = None
        self._orbs = self._make_orbs()
        self.bind("<Configure>", self._on_configure)
        self.bind("<Destroy>", lambda e: self._stop())

    # ── Orbes (geometría fija → estable entre ejecuciones) ────────────────────
    def _make_orbs(self):
        # Anclas sesgadas a la banda hero (sobre el buscador) y a los márgenes:
        # ahí es donde el canvas asoma de verdad (el centro lo tapa la tabla).
        # Elipses anchas para cubrir esas franjas con un campo glass continuo.
        # ax,    ay,    dx, dy, sx,   sy,   px,  py,  rw,  rh
        specs = [
            (0.50,  0.00, 34, 18, 0.10, 0.13, 0.0, 1.7, 430, 150),  # banda hero
            (0.05,  0.05, 42, 30, 0.16, 0.12, 1.1, 0.4, 205, 205),  # esquina sup. izq.
            (0.95,  0.09, 40, 34, 0.13, 0.17, 2.1, 0.6, 205, 215),  # esquina sup. der.
            (-0.02, 0.52, 30, 72, 0.12, 0.10, 3.0, 2.4, 150, 235),  # margen izq.
            (1.02,  0.58, 28, 66, 0.10, 0.14, 1.6, 1.2, 150, 235),  # margen der.
            (0.13,  1.02, 60, 30, 0.14, 0.12, 3.1, 0.3, 235, 160),  # base izq.
            (0.88,  1.03, 54, 28, 0.11, 0.13, 0.7, 2.0, 225, 150),  # base der.
        ]
        return [_Orb(color, peak, *s) for (color, peak), s in zip(S.LIVE_ORBS, specs)]

    # ── Resize: reconstruye gradiente + orbes (geometría fija) ────────────────
    def _on_configure(self, e):
        if e.width == self._cw and e.height == self._ch:
            return
        self._cw, self._ch = e.width, e.height
        self._rebuild()
        if not self._running:
            self._start()

    def _grad_color(self, y):
        t = min(max(y / max(self._ch - 1, 1), 0.0), 1.0)
        return mix(S.LIVE_GRAD_TOP, S.LIVE_GRAD_BOT, t)

    def _rebuild(self):
        self.delete("all")
        self._grad_dy = 0.0
        if self._cw <= 1 or self._ch <= 1:
            return
        self._draw_gradient()
        self._build_orbs()

    def _draw_gradient(self):
        # Sobredibuja arriba y abajo (GRAD_OVER) para poder desplazar el
        # gradiente verticalmente sin que aparezcan huecos en los bordes.
        for y in range(-GRAD_OVER, self._ch + GRAD_OVER, GRAD_STEP):
            self.create_rectangle(0, y, self._cw, y + GRAD_STEP, outline="",
                                  fill=self._grad_color(y), tags="grad")

    def _build_orbs(self):
        for i, orb in enumerate(self._orbs):
            orb.tag = f"orb{i}"
            cx, cy = orb.target(self._t, self._cw, self._ch)
            orb.cx, orb.cy = cx, cy
            base = self._grad_color(orb.ay * self._ch)   # mezcla contra el fondo en su ancla
            # De fuera (j=0, ≈base, invisible) hacia dentro (j=N-1, color pleno).
            for j in range(ORB_LAYERS):
                frac = j / (ORB_LAYERS - 1)
                scale = 1.0 - frac * 0.97
                rw, rh = orb.rw * scale, orb.rh * scale
                inten = orb.peak * (frac ** 1.7)
                self.create_oval(cx - rw, cy - rh, cx + rw, cy + rh, outline="",
                                 fill=mix(base, orb.color, inten), tags=orb.tag)

    # ── Animación: sólo traslada bloques (1 llamada Tcl por capa móvil) ───────
    def _animate(self):
        w, h = self._cw, self._ch
        # Gradiente: deriva vertical muy lenta (respira) — se mueve en bloque.
        gdy = GRAD_AMP * math.sin(GRAD_SPD * self._t)
        if gdy != self._grad_dy:
            self.move("grad", 0, gdy - self._grad_dy)
            self._grad_dy = gdy
        # Orbes: cada uno se traslada por el delta respecto a su centro previo.
        for orb in self._orbs:
            tx, ty = orb.target(self._t, w, h)
            self.move(orb.tag, tx - orb.cx, ty - orb.cy)
            orb.cx, orb.cy = tx, ty

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
        # Reprograma primero: el timer corre en paralelo al trabajo del frame,
        # así la cadencia se mantiene ~constante (~60 fps) en vez de sumar
        # intervalo + cómputo en cada vuelta.
        self._after = self.after(FPS_MS, self._tick)
        try:
            visible = self.winfo_viewable()
        except Exception:
            visible = True
        if visible and self._cw > 1:
            self._t += FPS_MS / 1000.0
            self._animate()
