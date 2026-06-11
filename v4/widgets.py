"""
widgets.py — Primitivos de UI reutilizables (tkinter puro, look glass).

Estos widgets no conocen la lógica de negocio: se les pasan textos y callbacks.
  · RoundedButton   — botón plano con jerarquía (primary / secondary / flat / ghost)
  · StatusBar       — barra de estado inferior con semántica (ok/info/warn/error/spin)
  · FocusField      — Entry envuelto en un marco con focus ring (+ icono y placeholder)
  · ScrollableFrame — contenedor vertical scrollable (canvas + rueda del ratón)
  · Chip / Badge    — etiquetas pequeñas (pill de color / contador)
  · Tooltip         — tooltip flotante para cualquier widget
"""
import tkinter as tk
import tkinter.font as tkfont

import styles as S
from core.utils import _hex_to_rgb, lerp_rgb

try:
    from PIL import Image, ImageDraw, ImageTk, ImageFilter, ImageChops
    _HAS_PIL = True
except Exception:                      # pragma: no cover
    _HAS_PIL = False

HAS_PIL = _HAS_PIL                     # para que otros módulos elijan su fallback


# ══════════════════════════════════════════════════════════════════════════════
#  HELPERS DE IMAGEN GLASS (rounded rect con AA, bisel, borde y sombra)
# ══════════════════════════════════════════════════════════════════════════════

def _v_grad(w, h, top, bot):
    """Imagen RGB de un gradiente vertical top→bot, de tamaño w×h."""
    h = max(int(h), 1)
    col = Image.new("RGB", (1, h))
    ld = col.load()
    for y in range(h):
        ld[0, y] = lerp_rgb(top, bot, y / max(h - 1, 1))
    return col.resize((max(int(w), 1), h))


def _v_grad_L(w, h, top, bot):
    """Igual que _v_grad pero en escala de grises (máscara de caída vertical)."""
    h = max(int(h), 1)
    col = Image.new("L", (1, h))
    ld = col.load()
    for y in range(h):
        ld[0, y] = int(top + (bot - top) * (y / max(h - 1, 1)))
    return col.resize((max(int(w), 1), h))


def glass_field_image(w, h, *, radius, surface, focused=False, pad=8, shadow=True):
    """Tarjeta glass redondeada como PhotoImage (gradiente + bisel + borde + sombra).

    Las esquinas/márgenes se pintan con `surface` para fundirse con lo que haya
    detrás (panel sólido o, en el buscador, el glow hero). `radius=None` → píldora.
    `shadow=False` evita la sombra (útil cuando flota sobre el glow, donde una
    sombra oscura crearía un halo visible)."""
    ss = 2
    w, h = max(int(w), 1), max(int(h), 1)
    W, H = w * ss, h * ss
    P = pad * ss
    box = [P, P, W - P, H - P]
    r = (box[3] - box[1]) // 2 if radius is None else int(radius * ss)
    r = max(1, min(r, (box[3] - box[1]) // 2))

    base = Image.new("RGB", (W, H), _hex_to_rgb(surface))

    # 1) Sombra difusa (rounded rect oscuro, desplazado hacia abajo y desenfocado)
    if shadow:
        sh = Image.new("L", (W, H), 0)
        ImageDraw.Draw(sh).rounded_rectangle(
            [box[0], box[1] + 3 * ss, box[2], box[3] + 3 * ss], radius=r, fill=110)
        sh = sh.filter(ImageFilter.GaussianBlur(5 * ss))
        base = Image.composite(Image.new("RGB", (W, H), S.SHADOW_RGB), base, sh)

    # 2) Glow índigo exterior al enfocar
    if focused:
        gl = Image.new("L", (W, H), 0)
        ImageDraw.Draw(gl).rounded_rectangle(box, radius=r, fill=255)
        gl = gl.filter(ImageFilter.GaussianBlur(7 * ss)).point(lambda v: int(v * 0.5))
        base = Image.composite(Image.new("RGB", (W, H), _hex_to_rgb(S.ACCENT)), base, gl)

    # 3) Relleno de vidrio (gradiente vertical)
    fill_mask = Image.new("L", (W, H), 0)
    ImageDraw.Draw(fill_mask).rounded_rectangle(box, radius=r, fill=255)
    grad = _v_grad(W, H, _hex_to_rgb(S.FIELD_TOP), _hex_to_rgb(S.FIELD_BOT))
    base = Image.composite(grad, base, fill_mask)

    # 4) Bisel superior (línea clara interior que decae hacia el centro)
    hi = Image.new("L", (W, H), 0)
    ImageDraw.Draw(hi).rounded_rectangle(
        [box[0] + ss, box[1] + ss, box[2] - ss, box[3] - ss],
        radius=max(r - ss, 1), outline=255, width=max(ss, 1))
    hi = ImageChops.multiply(hi, _v_grad_L(W, H, 255, 0)).point(lambda v: int(v * 0.55))
    base = Image.composite(Image.new("RGB", (W, H), _hex_to_rgb(S.FIELD_HILITE)), base, hi)

    # 5) Borde suave (índigo al enfocar)
    border = S.FIELD_BORDER_FOCUS if focused else S.FIELD_BORDER
    ImageDraw.Draw(base).rounded_rectangle(box, radius=r, outline=_hex_to_rgb(border),
                                           width=max(ss, 1))

    return ImageTk.PhotoImage(base.resize((w, h), Image.LANCZOS))


def _solid_alpha(size, rgb, alpha):
    """Capa RGBA de color sólido `rgb` cuyo canal alpha es la máscara `alpha`."""
    layer = Image.new("RGBA", size, rgb + (0,))
    layer.putalpha(alpha)
    return layer


def rounded_card_image(w, h, *, radius, margin, surface=None):
    """Tarjeta de contenido redondeada como PhotoImage RGBA (fondo transparente).

    Pensada para colocarse como ITEM del canvas del fondo vivo: fuera del
    contorno el alpha es 0, así las esquinas redondeadas dejan ver la animación
    de detrás sin componer nada por fotograma (coste cero en el tick). Lleva
    horneados la sombra difusa (sólo lados/base: arriba está el glow hero y una
    sombra ahí dibujaría un halo oscuro), el bisel superior y el borde suave.
    El interior es plano (`surface`) para fundirse con el Frame de contenido
    que vive encima. `margin` es el aire transparente donde respira la sombra.
    """
    ss = 2
    w, h = max(int(w), 1), max(int(h), 1)
    W, H = w * ss, h * ss
    M = margin * ss
    box = [M, M, W - M, H - M]
    r = max(1, min(int(radius * ss), (box[3] - box[1]) // 2))
    surface = surface if surface is not None else S.BG_CARD

    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))

    # 1) Sombra difusa, desplazada hacia abajo para no manchar el glow superior
    sh = Image.new("L", (W, H), 0)
    ImageDraw.Draw(sh).rounded_rectangle(
        [box[0], box[1] + 10 * ss, box[2], box[3] + 4 * ss], radius=r, fill=100)
    sh = sh.filter(ImageFilter.GaussianBlur(6 * ss))
    img = Image.alpha_composite(img, _solid_alpha((W, H), S.SHADOW_RGB, sh))

    # 2) Cuerpo plano (mismo color que el Frame interior → unión invisible)
    body = Image.new("L", (W, H), 0)
    ImageDraw.Draw(body).rounded_rectangle(box, radius=r, fill=255)
    img = Image.alpha_composite(img, _solid_alpha((W, H), _hex_to_rgb(surface), body))

    # 3) Bisel superior (línea clara interior que se apaga hacia abajo)
    hi = Image.new("L", (W, H), 0)
    ImageDraw.Draw(hi).rounded_rectangle(
        [box[0] + ss, box[1] + ss, box[2] - ss, box[3] - ss],
        radius=max(r - ss, 1), outline=255, width=max(ss, 1))
    hi = ImageChops.multiply(hi, _v_grad_L(W, H, 255, 0)).point(lambda v: int(v * 0.9))
    img = Image.alpha_composite(img, _solid_alpha((W, H), _hex_to_rgb(S.CARD_HILITE), hi))

    # 4) Borde suave de cierre
    bd = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(bd).rounded_rectangle(
        box, radius=r, outline=_hex_to_rgb(S.CARD_BORDER) + (255,), width=max(ss, 1))
    img = Image.alpha_composite(img, bd)

    return ImageTk.PhotoImage(img.resize((w, h), Image.LANCZOS))


# ══════════════════════════════════════════════════════════════════════════════
#  BOTÓN
# ══════════════════════════════════════════════════════════════════════════════

def _button_style(variant):
    """Paleta de cada variante de botón (reposo / hover / borde / padding)."""
    if variant == "secondary":
        return dict(bg=S.BG_GLASS, fg=S.ACCENT_SOFT, border=S.BORDER,
                    hover_bg=S.CHIP_HOVER, hover_border=S.ACCENT_SOFT,
                    hover_fg=S.ACCENT_VIOLET, padx=17, pady=10)
    if variant == "flat":
        return dict(bg=S.CHIP_BG, fg=S.TEXT_MUTE, border=S.CHIP_BORDER,
                    hover_bg=S.CHIP_HOVER, hover_border=S.ACCENT_SOFT,
                    hover_fg=S.ACCENT_SOFT, padx=14, pady=9)
    if variant == "ghost":
        return dict(bg=S.BG_PANEL, fg=S.TEXT_DIM, border=S.BG_PANEL,
                    hover_bg=S.BG_ELEV, hover_border=S.BG_ELEV,
                    hover_fg=S.TEXT, padx=11, pady=7)
    return dict(bg=S.ACCENT, fg=S.TEXT, border=S.ACCENT,            # primary
                hover_bg=S.PRIMARY_HOVER, hover_border=S.PRIMARY_HOVER,
                hover_fg=S.TEXT, padx=22, pady=11)


def _rounded_btn_image(w, h, radius, fill, border, border_w, surface):
    """Imagen RGB de una píldora redondeada con antialias real (supersample →
    LANCZOS). Esquinas pintadas con `surface` (se funden con el panel); encima un
    relleno con gradiente sutil + bisel superior (volumen) y un borde fino."""
    ss = 4
    w, h = max(int(w), 1), max(int(h), 1)
    W, H = w * ss, h * ss
    r = max(radius * ss, 1)
    img = Image.new("RGB", (W, H), surface)
    mask = Image.new("L", (W, H), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, W - 1, H - 1], radius=r, fill=255)

    # Relleno con gradiente sutil (más claro arriba → base abajo) → volumen
    top = tuple(min(255, c + 15) for c in fill)
    img = Image.composite(_v_grad(W, H, top, fill), img, mask)

    # Bisel superior: línea clara interior que decae hacia el centro
    hi = Image.new("L", (W, H), 0)
    ImageDraw.Draw(hi).rounded_rectangle([ss, ss, W - 1 - ss, H - 1 - ss],
                                         radius=max(r - ss, 1), outline=255,
                                         width=max(ss, 1))
    hi = ImageChops.multiply(hi, _v_grad_L(W, H, 255, 0)).point(lambda v: int(v * 0.45))
    hilite = tuple(min(255, c + 55) for c in fill)
    img = Image.composite(Image.new("RGB", (W, H), hilite), img, hi)

    # Borde fino
    bw = int(border_w * ss)
    if bw > 0 and border is not None and border != fill:
        ImageDraw.Draw(img).rounded_rectangle(
            [bw / 2, bw / 2, W - 1 - bw / 2, H - 1 - bw / 2],
            radius=max(r - bw / 2, 1), outline=border, width=bw)
    return ImageTk.PhotoImage(img.resize((w, h), Image.LANCZOS))


class _RoundedButtonCanvas(tk.Canvas):
    """Botón premium con esquinas verdaderamente redondeadas (imagen Pillow).

    El relleno se renderiza supersampleado y se reduce con LANCZOS, así los
    bordes quedan suaves (tk.Button sólo da rectángulos). El texto se dibuja
    nativo encima para mantenerlo nítido. Cuatro variantes:

    primary   → CTA índigo, texto blanco.
    secondary → vidrio con texto índigo; el borde pasa a índigo en hover.
    flat      → chip discreto (acciones terciarias del sidebar / toolbar).
    ghost     → sin fondo, solo texto que se aclara en hover.
    """
    def __init__(self, parent, text, command, *, variant="primary", font_size=10,
                 surface=None, **kw):
        self._variant = variant
        self._command = command
        self._text = text
        self._enabled = True
        self._hover = False
        self._style = _button_style(variant)
        self._font = S.font(font_size, "bold")
        self._fontobj = tkfont.Font(family=S.FONT_UI, size=font_size, weight="bold")
        self._surface = surface if surface is not None else S.BG_PANEL

        tw = self._fontobj.measure(text)
        th = self._fontobj.metrics("linespace")
        w = tw + 2 * self._style["padx"]
        h = th + 2 * self._style["pady"]
        super().__init__(parent, width=w, height=h, bg=self._surface,
                         highlightthickness=0, bd=0, takefocus=0, cursor="hand2")
        self._img_id = None
        self._photo = None
        self._txt_id = self.create_text(w // 2, h // 2, text=text,
                                        fill=self._style["fg"], font=self._font)
        self.bind("<Configure>", lambda e: self._render())
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-1>", self._on_click)

    # ── Render ──────────────────────────────────────────────────────────────────
    def _render(self):
        w, h = self.winfo_width(), self.winfo_height()
        if w <= 1 or h <= 1:
            return
        s = self._style
        if not self._enabled:
            fill, border, fg = S.BG_GLASS, S.BORDER, S.TEXT_DIM
        elif self._hover:
            fill, border, fg = s["hover_bg"], s["hover_border"], s["hover_fg"]
        else:
            fill, border, fg = s["bg"], s["border"], s["fg"]
        r = min(h // 2, S.RADIUS_CTRL)
        self._photo = _rounded_btn_image(
            w, h, r, _hex_to_rgb(fill), _hex_to_rgb(border), 1,
            _hex_to_rgb(self._surface))
        if self._img_id is None:
            self._img_id = self.create_image(0, 0, anchor="nw", image=self._photo)
        else:
            self.itemconfig(self._img_id, image=self._photo)
        self.tag_lower(self._img_id)
        self.coords(self._txt_id, w // 2, h // 2)
        self.itemconfig(self._txt_id, fill=fg, text=self._text)
        self.tag_raise(self._txt_id)

    # ── Interacción ─────────────────────────────────────────────────────────────
    def _on_enter(self, _):
        if self._enabled:
            self._hover = True
            self._render()

    def _on_leave(self, _):
        if self._enabled:
            self._hover = False
            self._render()

    def _on_click(self, _):
        if self._enabled and self._command:
            self._command()

    # ── API (compatible con tk.Button) ──────────────────────────────────────────
    def set_text(self, text):
        self._text = text
        self.config(width=self._fontobj.measure(text) + 2 * self._style["padx"])
        self._render()

    def set_enabled(self, enabled: bool):
        self._enabled = bool(enabled)
        self.config(cursor="hand2" if enabled else "arrow")
        self._hover = False
        self._render()


class _RoundedButtonFlat(tk.Button):
    """Fallback sin Pillow: botón plano con borde que se ilumina en hover."""
    def __init__(self, parent, text, command, *, variant="primary", font_size=10,
                 surface=None, **kw):
        self._variant  = variant
        self._cmd_real = command
        s = _button_style(variant)
        self._normal = s
        super().__init__(
            parent, text=text, command=command,
            bg=s["bg"], fg=s["fg"],
            activebackground=s["hover_bg"], activeforeground=s["hover_fg"],
            disabledforeground=S.TEXT_DIM,
            font=S.font(font_size, "bold"),
            relief="flat", bd=0, cursor="hand2",
            padx=s["padx"], pady=s["pady"], takefocus=0,
            highlightthickness=1,
            highlightbackground=s["border"], highlightcolor=s["border"],
            **kw,
        )
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)

    def _on_enter(self, _):
        if str(self["state"]) == "disabled":
            return
        s = self._normal
        self.config(bg=s["hover_bg"], fg=s["hover_fg"],
                    highlightbackground=s["hover_border"], highlightcolor=s["hover_border"])

    def _on_leave(self, _):
        if str(self["state"]) == "disabled":
            return
        s = self._normal
        self.config(bg=s["bg"], fg=s["fg"],
                    highlightbackground=s["border"], highlightcolor=s["border"])

    def set_text(self, text):
        self.config(text=text)

    def set_enabled(self, enabled: bool):
        if enabled:
            s = self._normal
            self.config(state="normal", bg=s["bg"], fg=s["fg"],
                        highlightbackground=s["border"], highlightcolor=s["border"],
                        command=self._cmd_real)
        else:
            self.config(state="disabled", bg=S.BG_GLASS, fg=S.TEXT_DIM,
                        highlightbackground=S.BORDER, highlightcolor=S.BORDER)


def RoundedButton(*args, **kw):
    """Crea el botón premium (Pillow) o, si no hay Pillow, el plano de respaldo."""
    cls = _RoundedButtonCanvas if _HAS_PIL else _RoundedButtonFlat
    return cls(*args, **kw)


# ══════════════════════════════════════════════════════════════════════════════
#  STATUS BAR
# ══════════════════════════════════════════════════════════════════════════════

class StatusBar(tk.Frame):
    """Barra de estado inferior: punto de color + mensaje semántico.

    El mensaje se compone de segmentos (etiquetas independientes) para poder
    mezclar tipografías y colores en una misma línea — clave para la
    confirmación de exportación, que resalta el nombre del archivo.
    """
    def __init__(self, parent):
        super().__init__(parent, bg=S.BG_DEEP, height=32)
        self.pack_propagate(False)
        self._dot = tk.Label(self, text="●", font=S.font(8), bg=S.BG_DEEP, fg=S.TEXT_DIM)
        self._dot.pack(side="left", padx=(20, 9))
        self._seg = tk.Frame(self, bg=S.BG_DEEP)
        self._seg.pack(side="left", fill="both", expand=True)
        self.set("Ready")

    # ── Composición de segmentos ──────────────────────────────────────────────
    def _clear(self):
        for w in self._seg.winfo_children():
            w.destroy()

    def _label(self, text, color, fnt, padx=0):
        tk.Label(self._seg, text=text, bg=S.BG_DEEP, fg=color, font=fnt
                 ).pack(side="left", padx=padx)

    def set(self, text, color=S.TEXT_DIM):
        self._clear()
        self._dot.config(fg=color)
        self._label(text, color, S.font(9))
        self.update_idletasks()

    def ok(self, text):    self.set(f"✔  {text}", S.SUCCESS)
    def info(self, text):  self.set(f"→  {text}", S.ACCENT_SOFT)
    def warn(self, text):  self.set(f"⚠  {text}", S.WARNING)
    def error(self, text): self.set(f"✖  {text}", S.DANGER)
    def spin(self, text):  self.set(f"◌  {text}", S.ACCENT)

    def export_done(self, filename, size_kb):
        """Confirmación de exportación con jerarquía tipográfica y el nombre del
        archivo destacado en un chip índigo:
            ✓  Exportado   [ nombre_archivo.md ]   12.3 KB
        """
        self._clear()
        self._dot.config(fg=S.SUCCESS)
        self._label("✓", S.SUCCESS, S.font(11, "bold"), padx=(0, 9))
        self._label("Exported", S.TEXT_SOFT, S.font(9, "bold"))
        chip = tk.Label(self._seg, text=filename, bg=S.CHIP_BG, fg=S.ACCENT_SOFT,
                        font=S.mono(9, "bold"), padx=9, pady=2,
                        highlightthickness=1, highlightbackground=S.CHIP_BORDER,
                        highlightcolor=S.CHIP_BORDER)
        chip.pack(side="left", padx=11)
        self._label(f"{size_kb:.1f} KB", S.TEXT_DIM, S.font(9))
        self.update_idletasks()


# ══════════════════════════════════════════════════════════════════════════════
#  CAMPO DE ENTRADA CON FOCUS RING
# ══════════════════════════════════════════════════════════════════════════════

class _FocusFieldGlass(tk.Canvas):
    """Campo glass premium: tarjeta Pillow redondeada (gradiente + bisel + borde +
    sombra) con un Entry nativo encima. Soporta icono y placeholder. Al enfocar,
    el borde se vuelve índigo y aparece un glow suave.

    Las esquinas se funden con `surface` (panel sólido, o el glow hero para el
    buscador). Acceso al texto con `.value` / `.var`; el Entry vive en `.entry`.
    """
    def __init__(self, parent, *, textvariable=None, font=None, icon=None,
                 placeholder=None, mono=False, surface=S.BG_PANEL,
                 radius=None, height=None, shadow=True):
        self.var = textvariable or tk.StringVar()
        self._font = font or (S.mono(9) if mono else S.font(10))
        self._fontobj = tkfont.Font(font=self._font)
        self._placeholder = placeholder
        self._showing_ph = False
        self._surface = surface
        self._radius = radius
        self._icon = icon
        self._shadow = shadow
        self._focused = False
        self._pad = 8                       # margen exterior (sombra / glow)
        self._last_wh = (0, 0)

        ls = self._fontobj.metrics("linespace")
        inner = 9 if not mono else 7
        h = height or (ls + 2 * inner + 2 * self._pad)
        super().__init__(parent, height=h, bg=surface, highlightthickness=0,
                         bd=0, takefocus=0)

        self._img_id = None
        self._photo = None
        self._icon_id = None
        self.entry = tk.Entry(self, textvariable=self.var, font=self._font,
                              bg=S.FIELD_MID, fg=S.TEXT, insertbackground=S.ACCENT,
                              relief="flat", bd=0, highlightthickness=0)
        self._entry_win = self.create_window(0, 0, anchor="w", window=self.entry)

        self.entry.bind("<FocusIn>", self._on_focus_in, add="+")
        self.entry.bind("<FocusOut>", self._on_focus_out, add="+")
        self.bind("<Configure>", lambda e: self._redraw())

        if placeholder:
            self._apply_placeholder()

    # ── Pintado ─────────────────────────────────────────────────────────────────
    def _redraw(self):
        w, h = self.winfo_width(), self.winfo_height()
        if w <= 1 or h <= 1:
            return
        if (w, h) != self._last_wh or self._dirty():
            self._last_wh = (w, h)
            self._photo = glass_field_image(
                w, h, radius=self._radius, surface=self._surface,
                focused=self._focused, pad=self._pad, shadow=self._shadow)
            if self._img_id is None:
                self._img_id = self.create_image(0, 0, anchor="nw", image=self._photo)
            else:
                self.itemconfig(self._img_id, image=self._photo)
            self.tag_lower(self._img_id)
        # Posicionar icono + entry sobre la tarjeta
        cy = h // 2
        left = self._pad + 16
        if self._icon is not None:
            if self._icon_id is None:
                self._icon_id = self.create_text(left, cy, text=self._icon,
                                                 fill=S.TEXT_DIM, font=S.font(12),
                                                 anchor="w")
            else:
                self.coords(self._icon_id, left, cy)
            left += 24
        right = w - self._pad - 16
        self.coords(self._entry_win, left, cy)
        self.itemconfig(self._entry_win, width=max(right - left, 1),
                        height=self._fontobj.metrics("linespace") + 4)

    def _dirty(self):
        """Marca para forzar re-render cuando cambia el estado de foco."""
        d = getattr(self, "_focus_dirty", False)
        self._focus_dirty = False
        return d

    def _rerender(self):
        self._focus_dirty = True
        self._redraw()

    # ── Focus ring ────────────────────────────────────────────────────────────
    def _on_focus_in(self, _):
        self._focused = True
        self._rerender()
        if self._showing_ph:
            self._showing_ph = False
            self.var.set("")
            self.entry.config(fg=S.TEXT)

    def _on_focus_out(self, _):
        self._focused = False
        self._rerender()
        if self._placeholder and not self.var.get().strip():
            self._apply_placeholder()

    def _apply_placeholder(self):
        self._showing_ph = True
        self.entry.config(fg=S.TEXT_FAINT)
        self.var.set(self._placeholder)

    # ── Valor ─────────────────────────────────────────────────────────────────
    @property
    def value(self) -> str:
        return "" if self._showing_ph else self.var.get()

    @value.setter
    def value(self, text: str):
        self._showing_ph = False
        self.entry.config(fg=S.TEXT)
        self.var.set(text)

    def is_placeholder(self) -> bool:
        return self._showing_ph


class _FocusFieldFlat(tk.Frame):
    """Fallback sin Pillow: Entry en un marco con borde que se ilumina al enfocar.

    Acepta (e ignora) los kwargs estéticos de la variante glass —radius, shadow,
    surface…— para que los llamadores no tengan que distinguir variantes."""
    def __init__(self, parent, *, textvariable=None, font=None, icon=None,
                 placeholder=None, mono=False, surface=S.BG_PANEL,
                 radius=None, height=None, shadow=True):
        super().__init__(parent, bg=S.BG_PANEL, bd=0, highlightthickness=1,
                         highlightbackground=S.BORDER, highlightcolor=S.BORDER)
        self.var = textvariable or tk.StringVar()
        self._font = font or (S.mono(9) if mono else S.font(10))
        self._placeholder = placeholder
        self._showing_ph = False

        if icon is not None:
            tk.Label(self, text=icon, bg=S.BG_PANEL, fg=S.TEXT_DIM,
                     font=S.font(11)).pack(side="left", padx=(11, 6))

        self.entry = tk.Entry(self, textvariable=self.var, font=self._font,
                              bg=S.BG_PANEL, fg=S.TEXT, insertbackground=S.ACCENT,
                              relief="flat", bd=0, highlightthickness=0)
        self.entry.pack(side="left", fill="x", expand=True,
                        padx=(0 if icon is not None else 12, 12), ipady=8)

        self.entry.bind("<FocusIn>", self._on_focus_in, add="+")
        self.entry.bind("<FocusOut>", self._on_focus_out, add="+")

        if placeholder:
            self._apply_placeholder()

    def _on_focus_in(self, _):
        self.config(highlightbackground=S.BORDER_FOCUS, highlightcolor=S.BORDER_FOCUS)
        if self._showing_ph:
            self._showing_ph = False
            self.var.set("")
            self.entry.config(fg=S.TEXT)

    def _on_focus_out(self, _):
        self.config(highlightbackground=S.BORDER, highlightcolor=S.BORDER)
        if self._placeholder and not self.var.get().strip():
            self._apply_placeholder()

    def _apply_placeholder(self):
        self._showing_ph = True
        self.entry.config(fg=S.TEXT_FAINT)
        self.var.set(self._placeholder)

    @property
    def value(self) -> str:
        return "" if self._showing_ph else self.var.get()

    @value.setter
    def value(self, text: str):
        self._showing_ph = False
        self.entry.config(fg=S.TEXT)
        self.var.set(text)

    def is_placeholder(self) -> bool:
        return self._showing_ph


def FocusField(*args, **kw):
    """Crea el campo glass (Pillow) o el plano de respaldo si no hay Pillow."""
    cls = _FocusFieldGlass if _HAS_PIL else _FocusFieldFlat
    return cls(*args, **kw)


# ══════════════════════════════════════════════════════════════════════════════
#  SCROLLBAR GLASS (cápsula slim redondeada, dibujada a mano)
# ══════════════════════════════════════════════════════════════════════════════

class GlassScrollbar(tk.Canvas):
    """Scrollbar vertical slim y moderna, acorde al glassmorphism de la app.

    Implementa el protocolo de tk.Scrollbar (`set` como yscrollcommand + un
    `command` tipo yview), así que es un reemplazo directo para Canvas o Text.
    Sin flechas: una píldora redondeada con antialias real (imagen Pillow), un
    riel sutil y un sheen vertical que le da profundidad. Se ilumina en hover y se
    oculta cuando todo el contenido cabe en pantalla.

    El render con imagen elimina las "rayas duras" del trazado vectorial de
    tkinter (que no tiene antialias): la cápsula se dibuja supersampleada y se
    reduce con LANCZOS, así los bordes y las tapas quedan suaves y simétricos. Si
    Pillow no está disponible, cae a un trazado vectorial equivalente.
    """
    def __init__(self, parent, command, *, bg=S.BG_DEEP, width=S.SCROLL_W):
        super().__init__(parent, width=width, bg=bg, highlightthickness=0, bd=0,
                         takefocus=0)
        self._command = command            # callable estilo yview
        self._first, self._last = 0.0, 1.0
        self._pad = 2                       # margen del thumb respecto al borde
        self._track_pad = 4                 # margen del riel (más estrecho que el thumb)
        self._min_thumb = 34                # alto mínimo legible del thumb (px)
        self._hover = False
        self._drag_dy = None                # offset del ratón dentro del thumb
        self._img_id = None                 # item de imagen en el canvas
        self._photo = None                  # ref viva de la PhotoImage (anti-GC)
        self.bind("<Configure>", lambda e: self._redraw())
        self.bind("<Button-1>", self._on_press)
        self.bind("<B1-Motion>", self._on_motion)
        self.bind("<ButtonRelease-1>", lambda e: self._end_drag())
        self.bind("<Enter>", lambda e: self._set_hover(True))
        self.bind("<Leave>", lambda e: self._set_hover(False))

    # ── Protocolo yscrollcommand ──────────────────────────────────────────────
    def set(self, first, last):
        self._first, self._last = float(first), float(last)
        self._redraw()

    # ── Geometría del thumb (coordenadas de canvas) ───────────────────────────
    def _thumb_bounds(self):
        h = self.winfo_height()
        if h <= 1 or (self._first <= 0.0 and self._last >= 1.0):
            return None                     # contenido completo → sin thumb
        top, bot = self._first * h, self._last * h
        if bot - top < self._min_thumb:     # respeta un tamaño mínimo
            mid = (top + bot) / 2
            top, bot = mid - self._min_thumb / 2, mid + self._min_thumb / 2
            if top < 0:   top, bot = 0, self._min_thumb
            if bot > h:   top, bot = h - self._min_thumb, h
        return top, bot

    # ── Pintado ───────────────────────────────────────────────────────────────
    def _redraw(self):
        if not _HAS_PIL:
            self._redraw_vector()
            return
        photo = self._render_strip()
        if photo is None:                   # contenido completo → barra oculta
            if self._img_id is not None:
                self.delete(self._img_id)
                self._img_id = None
            self._photo = None
            return
        self._photo = photo
        if self._img_id is None:
            self._img_id = self.create_image(0, 0, anchor="nw", image=photo)
        else:
            self.itemconfig(self._img_id, image=photo)

    def _render_strip(self):
        """Compone riel + thumb en una sola imagen RGBA (supersample → LANCZOS).
        Devuelve una PhotoImage, o None si no debe verse barra."""
        w, h = self.winfo_width(), self.winfo_height()
        b = self._thumb_bounds()
        if w <= 1 or h <= 1 or b is None:
            return None
        ss = 4
        W, H = w * ss, h * ss
        img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # Riel: píldora estrecha de altura completa, con alpha sutil (sin línea dura).
        tp = self._track_pad * ss
        tr = _hex_to_rgb(S.SCROLL_TRACK)
        draw.rounded_rectangle([tp, tp, W - tp, H - tp], radius=(W - 2 * tp) / 2,
                               fill=(tr[0], tr[1], tr[2], S.SCROLL_TRACK_ALPHA))

        # Thumb: píldora con sheen vertical (más claro arriba → base abajo).
        top, bot = b
        pad = self._pad * ss
        x0, x1 = pad, W - pad
        y0 = int(top * ss) + pad
        y1 = int(bot * ss) - pad
        tw = int(x1 - x0)
        if y1 - y0 < tw:                    # nunca más corto que su diámetro
            y1 = y0 + tw
        th = y1 - y0
        hovering = self._hover or self._drag_dy is not None
        c_top = _hex_to_rgb(S.SCROLL_THUMB_TOP_H if hovering else S.SCROLL_THUMB_TOP)
        c_bot = _hex_to_rgb(S.SCROLL_THUMB_BOT_H if hovering else S.SCROLL_THUMB_BOT)
        grad = self._v_gradient(tw, th, c_top, c_bot)
        mask = Image.new("L", (tw, th), 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, tw - 1, th - 1],
                                               radius=tw / 2, fill=255)
        img.paste(grad, (int(x0), int(y0)), mask)

        return ImageTk.PhotoImage(img.resize((w, h), Image.LANCZOS))

    @staticmethod
    def _v_gradient(w, h, top, bot):
        """Columna de gradiente vertical top→bot, estirada a w×h."""
        h = max(h, 1)
        col = Image.new("RGB", (1, h))
        ld = col.load()
        for y in range(h):
            ld[0, y] = lerp_rgb(top, bot, y / max(h - 1, 1))
        return col.resize((max(w, 1), h))

    # ── Fallback vectorial (sin Pillow) ───────────────────────────────────────
    def _redraw_vector(self):
        self.delete("all")
        if self._thumb_bounds() is None:
            return
        h, w = self.winfo_height(), self.winfo_width()
        self._capsule(self._track_pad, self._pad, w - self._track_pad,
                      h - self._pad, S.SCROLL_TRACK, tag="track")
        top, bot = self._thumb_bounds()
        hovering = self._hover or self._drag_dy is not None
        rim  = S.SCROLL_THUMB if hovering else S.SCROLL_THUMB_BASE
        core = S.SCROLL_THUMB_HOVER if hovering else S.SCROLL_THUMB
        x0, x1 = self._pad, w - self._pad
        y0, y1 = top + self._pad, bot - self._pad
        self._capsule(x0, y0, x1, y1, rim, tag="thumb")
        ci, cj = 2, 3
        if (x1 - x0) > 2 * ci and (y1 - y0) > 2 * cj:
            self._capsule(x0 + ci, y0 + cj, x1 - ci, y1 - cj, core, tag="thumb")

    def _capsule(self, x0, y0, x1, y1, color, *, tag="thumb"):
        """Rectángulo con extremos semicirculares (pill vertical)."""
        if y1 - y0 < 2:
            y1 = y0 + 2
        d = x1 - x0
        self.create_rectangle(x0, y0 + d / 2, x1, y1 - d / 2,
                              fill=color, outline="", tags=tag)
        self.create_oval(x0, y0, x1, y0 + d, fill=color, outline="", tags=tag)
        self.create_oval(x0, y1 - d, x1, y1, fill=color, outline="", tags=tag)

    # ── Interacción ───────────────────────────────────────────────────────────
    def _set_hover(self, on):
        self._hover = on
        self._redraw()

    def _on_press(self, e):
        b = self._thumb_bounds()
        if not b:
            return
        top, bot = b
        if top <= e.y <= bot:
            self._drag_dy = e.y - top        # empezar arrastre
            self._redraw()
        else:
            self._command("scroll", 1 if e.y > bot else -1, "pages")

    def _on_motion(self, e):
        if self._drag_dy is None:
            return
        h = self.winfo_height()
        if h > 1:
            frac = (e.y - self._drag_dy) / h
            self._command("moveto", max(0.0, min(1.0, frac)))

    def _end_drag(self):
        self._drag_dy = None
        self._redraw()


# ══════════════════════════════════════════════════════════════════════════════
#  CONTENEDOR SCROLLABLE
# ══════════════════════════════════════════════════════════════════════════════

class ScrollableFrame(tk.Frame):
    """Canvas + frame interior con scroll vertical y rueda del ratón.

    Añade los hijos a `.body`. El ancho del interior sigue al del canvas para
    que las filas puedan estirarse horizontalmente.
    """
    def __init__(self, parent, *, bg=S.BG_DEEP):
        super().__init__(parent, bg=bg)
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0)
        self._sb = GlassScrollbar(self, self.canvas.yview, bg=bg)
        self.canvas.configure(yscrollcommand=self._sb.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self._sb.pack(side="right", fill="y")

        self.body = tk.Frame(self.canvas, bg=bg)
        self._win = self.canvas.create_window((0, 0), window=self.body, anchor="nw")

        self.body.bind("<Configure>",
                       lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>",
                         lambda e: self.canvas.itemconfig(self._win, width=e.width))

        # Rueda del ratón sólo mientras el cursor está dentro
        self.canvas.bind("<Enter>", self._bind_wheel)
        self.canvas.bind("<Leave>", self._unbind_wheel)

    def _bind_wheel(self, _):
        self.canvas.bind_all("<MouseWheel>", self._on_wheel)
        self.canvas.bind_all("<Button-4>", self._on_wheel)
        self.canvas.bind_all("<Button-5>", self._on_wheel)

    def _unbind_wheel(self, _):
        self.canvas.unbind_all("<MouseWheel>")
        self.canvas.unbind_all("<Button-4>")
        self.canvas.unbind_all("<Button-5>")

    def _on_wheel(self, event):
        if event.num == 4:
            delta = -1
        elif event.num == 5:
            delta = 1
        else:
            delta = -1 if event.delta > 0 else 1
        self.canvas.yview_scroll(delta, "units")

    def scroll_to_top(self):
        self.canvas.yview_moveto(0.0)

    def clear(self):
        for child in self.body.winfo_children():
            child.destroy()


# ══════════════════════════════════════════════════════════════════════════════
#  CHIP / BADGE
# ══════════════════════════════════════════════════════════════════════════════

def make_chip(parent, text, fg, bg, *, font_size=8):
    """Pill de color discreta (p. ej. nombre de proyecto)."""
    return tk.Label(parent, text=text, bg=bg, fg=fg,
                    font=S.font(font_size, "bold"), padx=8, pady=2)


def make_badge(parent, text, *, fg=S.ACCENT_SOFT, bg=S.BG_ELEV, font_size=8):
    """Badge numérico (contador de mensajes / sesiones)."""
    return tk.Label(parent, text=str(text), bg=bg, fg=fg,
                    font=S.font(font_size, "bold"), padx=7, pady=1)


# ══════════════════════════════════════════════════════════════════════════════
#  TOOLTIP
# ══════════════════════════════════════════════════════════════════════════════

class Tooltip:
    """Tooltip flotante reutilizable. `text_getter` puede ser str o callable."""
    def __init__(self, widget, text_getter, *, mono=True):
        self._w = widget
        self._get = text_getter
        self._mono = mono
        self._tip = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", lambda e: self.hide(), add="+")
        widget.bind("<ButtonPress>", lambda e: self.hide(), add="+")

    def _text(self):
        return self._get() if callable(self._get) else self._get

    def _schedule(self, event):
        text = self._text()
        if text:
            self.show(text, event.x_root, event.y_root)

    def show(self, text, x, y):
        self.hide()
        self._tip = tk.Toplevel(self._w)
        self._tip.wm_overrideredirect(True)
        self._tip.wm_geometry(f"+{x + 14}+{y + 18}")
        self._tip.configure(bg=S.BORDER)  # marco de 1px
        tk.Label(self._tip, text=text,
                 font=S.mono(9) if self._mono else S.font(9),
                 bg=S.BG_GLASS, fg=S.TEXT_MUTE, padx=10, pady=6,
                 justify="left", wraplength=460).pack(padx=1, pady=1)

    def hide(self):
        if self._tip is not None:
            try:
                self._tip.destroy()
            except Exception:
                pass
            self._tip = None
