"""
ui/living_background.py — Fondo "vivo" premium del área principal.

Replica el fondo de la extensión web (gradiente oscuro + orbes radiales borrosos
con `filter: blur(40px)` y `opacity`) que tkinter NO puede dar por sí solo: sus
óvalos no tienen antialias ni blur, así que producían bordes dentados, banding y
costuras. Aquí el fondo se compone como una IMAGEN con Pillow → blur y antialias
reales, denso y opaco como en la extensión.

Rendimiento (60 fps reales, fluido y sin tirones):
  · Se pre-calcula UNA sola vez, en un hilo, un loop SIN COSTURAS de N fotogramas
    a baja resolución (los orbes y el blur quedan horneados en cada fotograma).
    Memoria mínima y todo el coste pesado queda amortizado de entrada.
  · Cada tick (~60 fps) sólo escala el fotograma actual al tamaño del lienzo
    (BILINEAR, ~4 ms) y lo vuelca EN SITIO sobre la misma PhotoImage con
    `.paste()` —sin reasignar imágenes Tk ni recolorear nada—. El pacing es
    estable → fluidez real, no la sensación de bajo FPS del enfoque anterior.

El loop es perfectamente periódico (toda deriva es sin(2π·k·i/N) con k entero),
así que al volver al fotograma 0 no hay salto. La paleta vive en `styles.py`.

Se coloca DETRÁS del contenido del área central y asoma por la banda hero (sobre
el buscador) y los márgenes. Si Pillow no estuviera disponible, cae a un degradado
estático para que la app nunca rompa.
"""
import math
import random
import threading
import tkinter as tk

import styles as S
from core.utils import _hex_to_rgb, lerp_rgb

try:
    from PIL import Image, ImageFilter, ImageTk
    _HAS_PIL = True
except Exception:                      # pragma: no cover
    _HAS_PIL = False


# ── Parámetros de render ──────────────────────────────────────────────────────
FPS_MS      = 16        # ~60 fps
LOOP_FRAMES = 260       # fotogramas del loop → ~4.3 s a 60 fps (deriva lenta)
IW, IH      = 252, 240  # lienzo interno (baja res); se estira al tamaño real
DRIFT_M     = 16        # margen vertical para la respiración del gradiente (px)
BLUR        = IW * 0.058  # radio de blur ≈ filter: blur() de la extensión
GLOW_D      = 200       # diámetro del glow radial base (se reescala por orbe)

# Orbes: glow radial índigo/violeta compuesto por alpha (como las .orb de la
# extensión: radial-gradient + opacity). Bias a la banda hero (arriba) y a los
# márgenes —donde el fondo asoma de verdad—; abajo queda oscuro (lo tapa la tabla).
#   color,        alpha, ax,    ay,    rad,  drx,  dry,  bre,  fx, fy, fb, phase
_ORBS = [
    (S.ACCENT,        0.95, 0.50,  0.00, 0.62, 0.05, 0.06, 0.10, 1, 1, 2, 0.0),  # hero central · índigo
    (S.ACCENT_SOFT,   0.92, 0.13,  0.04, 0.40, 0.06, 0.05, 0.12, 1, 2, 2, 1.1),  # hero izq · índigo claro
    (S.ACCENT_VIOLET, 0.90, 0.88,  0.05, 0.40, 0.06, 0.05, 0.12, 2, 1, 2, 2.0),  # hero der · violeta
    (S.ACCENT_VIOLET, 0.70, 0.30,  0.02, 0.30, 0.07, 0.05, 0.14, 2, 1, 3, 3.1),  # acento hero · violeta
    (S.ACCENT_SOFT,   0.70, 0.70,  0.03, 0.30, 0.07, 0.05, 0.14, 1, 2, 3, 0.7),  # acento hero · índigo claro
    (S.ACCENT,        0.58, -0.04, 0.46, 0.34, 0.04, 0.08, 0.12, 1, 1, 2, 2.4),  # margen izq · índigo
    (S.ACCENT,        0.58, 1.04,  0.52, 0.34, 0.04, 0.08, 0.12, 1, 1, 2, 1.2),  # margen der · índigo
]


def _smoothstep(t):
    return t * t * (3.0 - 2.0 * t)


class LivingBackground(tk.Canvas):
    """Canvas que muestra el fondo animado (place + lower)."""

    def __init__(self, parent):
        super().__init__(parent, highlightthickness=0, bd=0,
                         bg=S.LIVE_GRAD_BOT, takefocus=0)
        # OJO: tkinter reserva self._w para la ruta del widget → usamos _cw/_ch.
        self._cw = self._ch = 0
        self._frames = []          # lista de PIL.Image (baja res), loop sin costuras
        self._pending = None       # frames recién calculados en el hilo (handoff)
        self._idx = 0
        self._photo = None         # ImageTk.PhotoImage reutilizada (paste en sitio)
        self._pw = self._ph = 0    # tamaño actual de _photo
        self._img_id = None
        self._running = False
        self._after = None
        self._build_started = False
        self.bind("<Configure>", self._on_configure)
        self.bind("<Destroy>", lambda e: self._stop())

    # ── Ciclo de vida ─────────────────────────────────────────────────────────
    def _on_configure(self, e):
        if e.width == self._cw and e.height == self._ch:
            return
        self._cw, self._ch = e.width, e.height
        if not _HAS_PIL:
            self._draw_static_gradient()
            return
        if not self._build_started and self._cw > 1:
            self._build_started = True
            threading.Thread(target=self._build_frames, daemon=True).start()
        if not self._running and self._cw > 1:
            self._start()

    # ── Pre-cálculo del loop (en hilo, sólo Pillow → sin tocar Tk) ─────────────
    def _build_frames(self):
        grad = self._make_gradient()          # gradiente alto (con margen de deriva)
        glow = self._make_glow()              # glow radial base (canal alpha)
        frames = []
        for i in range(LOOP_FRAMES):
            frames.append(self._compose(i, grad, glow))
        # Handoff seguro al hilo principal: asignación de referencia (atómica por
        # el GIL). El _tick (hilo principal) la recoge → sin after() entre hilos.
        self._pending = frames

    def _make_gradient(self):
        """Gradiente vertical índigo→oscuro, más alto que IH para poder respirar
        (deriva vertical) recortándolo en distinta Y por fotograma."""
        top = _hex_to_rgb(S.LIVE_GRAD_TOP)
        bot = _hex_to_rgb(S.LIVE_GRAD_BOT)
        gh = IH + 2 * DRIFT_M
        rnd = random.Random(7)           # determinista → loop reproducible
        data = []
        for y in range(gh):
            te = (y / (gh - 1)) ** 1.18  # ensancha el resplandor superior (hero)
            r, g, b = lerp_rgb(top, bot, te)
            for _ in range(IW):
                j = rnd.randint(-2, 2)   # dither sutil → rompe el banding en zonas oscuras
                data.append((r + j, g + j, b + j))
        img = Image.new("RGB", (IW, gh))
        img.putdata(data)
        return img

    def _make_glow(self):
        """Glow radial suave (canal 'L' usado como alpha): centro pleno → 0 en el
        borde con caída smoothstep, para un orbe borroso sin anillos."""
        d = GLOW_D
        g = Image.new("L", (d, d), 0)
        px = g.load()
        c = (d - 1) / 2.0
        r0 = d / 2.0
        for y in range(d):
            for x in range(d):
                r = math.hypot(x - c, y - c) / r0
                if r >= 1.0:
                    continue
                v = _smoothstep(1.0 - r)
                px[x, y] = int(255 * v * v)   # núcleo denso, halo suave
        return g

    def _compose(self, i, grad, glow):
        """Compone un fotograma: gradiente (con deriva) + orbes por alpha + blur."""
        p = i / LOOP_FRAMES
        off = DRIFT_M + int(round(DRIFT_M * math.sin(2 * math.pi * p)))
        base = grad.crop((0, off, IW, off + IH))
        for (color, alpha, ax, ay, rad, drx, dry, bre, fx, fy, fb, ph) in _ORBS:
            breathe = 1.0 + bre * math.sin(2 * math.pi * fb * p + ph)
            size = max(8, int(2 * rad * IW * breathe))
            cx = ax * IW + drx * IW * math.sin(2 * math.pi * fx * p + ph)
            cy = ay * IH + dry * IH * math.cos(2 * math.pi * fy * p + ph)
            mask = glow.resize((size, size), Image.BILINEAR)
            if alpha < 0.999:
                mask = mask.point(lambda v, a=alpha: int(v * a))
            sol = Image.new("RGB", (size, size), _hex_to_rgb(color))
            base.paste(sol, (int(cx - size / 2), int(cy - size / 2)), mask)
        return base.filter(ImageFilter.GaussianBlur(BLUR))

    # ── Bucle de animación (hilo principal) ───────────────────────────────────
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
        # Reprograma primero → cadencia ~constante (~60 fps) sin acumular cómputo.
        self._after = self.after(FPS_MS, self._tick)
        if self._pending is not None:        # frames listos desde el hilo
            self._frames, self._pending = self._pending, None
        if not self._frames or self._cw <= 1:
            return
        try:
            if not self.winfo_viewable():
                return
        except Exception:
            pass
        self._idx = (self._idx + 1) % len(self._frames)
        big = self._frames[self._idx].resize((self._cw, self._ch), Image.BILINEAR)
        if self._photo is None or (self._pw, self._ph) != (self._cw, self._ch):
            self._photo = ImageTk.PhotoImage(big)
            self._pw, self._ph = self._cw, self._ch
            if self._img_id is None:
                self._img_id = self.create_image(0, 0, anchor="nw", image=self._photo)
            else:
                self.itemconfig(self._img_id, image=self._photo)
        else:
            self._photo.paste(big)        # vuelca en sitio → sin reasignar imagen Tk

    # ── Fallback sin Pillow: degradado estático (la app nunca rompe) ──────────
    def _draw_static_gradient(self):
        self.delete("all")
        if self._cw <= 1 or self._ch <= 1:
            return
        top = _hex_to_rgb(S.LIVE_GRAD_TOP)
        bot = _hex_to_rgb(S.LIVE_GRAD_BOT)
        step = 4
        from core.utils import rgb_hex
        for y in range(0, self._ch, step):
            t = (y / max(self._ch - 1, 1)) ** 1.18
            self.create_rectangle(0, y, self._cw, y + step, outline="",
                                  fill=rgb_hex(*lerp_rgb(top, bot, t)))
