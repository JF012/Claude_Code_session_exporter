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

import styles as S


# ══════════════════════════════════════════════════════════════════════════════
#  BOTÓN
# ══════════════════════════════════════════════════════════════════════════════

class RoundedButton(tk.Button):
    """Botón plano con borde que se ilumina en hover. Cuatro variantes visuales.

    primary   → CTA índigo, texto blanco.
    secondary → vidrio con texto índigo; el borde pasa a índigo en hover.
    flat      → chip discreto (acciones terciarias del sidebar / toolbar).
    ghost     → sin fondo, solo texto que se aclara en hover.
    """
    def __init__(self, parent, text, command, *, variant="primary", font_size=10, **kw):
        self._variant  = variant
        self._cmd_real = command
        s = self._style_for(variant)
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

    @staticmethod
    def _style_for(variant):
        if variant == "secondary":
            return dict(bg=S.BG_GLASS, fg=S.ACCENT_SOFT, border=S.BORDER,
                        hover_bg=S.BG_GLASS, hover_border=S.ACCENT_SOFT,
                        hover_fg=S.ACCENT_VIOLET, padx=16, pady=9)
        if variant == "flat":
            return dict(bg=S.CHIP_BG, fg=S.TEXT_MUTE, border=S.CHIP_BORDER,
                        hover_bg=S.CHIP_HOVER, hover_border=S.ACCENT_SOFT,
                        hover_fg=S.ACCENT_SOFT, padx=13, pady=8)
        if variant == "ghost":
            return dict(bg=S.BG_PANEL, fg=S.TEXT_DIM, border=S.BG_PANEL,
                        hover_bg=S.BG_PANEL, hover_border=S.BG_PANEL,
                        hover_fg=S.TEXT, padx=10, pady=6)
        return dict(bg=S.ACCENT, fg=S.TEXT, border=S.ACCENT,            # primary
                    hover_bg=S.PRIMARY_HOVER, hover_border=S.PRIMARY_HOVER,
                    hover_fg=S.TEXT, padx=22, pady=11)

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


# ══════════════════════════════════════════════════════════════════════════════
#  STATUS BAR
# ══════════════════════════════════════════════════════════════════════════════

class StatusBar(tk.Frame):
    """Barra de estado inferior con un punto de color y un mensaje semántico."""
    def __init__(self, parent):
        super().__init__(parent, bg=S.BG_DEEP, height=30)
        self._dot = tk.Label(self, text="●", font=S.font(8), bg=S.BG_DEEP, fg=S.TEXT_DIM)
        self._msg = tk.Label(self, text="Listo", font=S.font(9),
                             bg=S.BG_DEEP, fg=S.TEXT_DIM, anchor="w")
        self._dot.pack(side="left", padx=(20, 7), pady=7)
        self._msg.pack(side="left", fill="x", expand=True, pady=7)

    def set(self, text, color=S.TEXT_DIM):
        self._msg.config(text=text, fg=color)
        self._dot.config(fg=color)
        self.update_idletasks()

    def ok(self, text):    self.set(f"✔  {text}", S.SUCCESS)
    def info(self, text):  self.set(f"→  {text}", S.ACCENT_SOFT)
    def warn(self, text):  self.set(f"⚠  {text}", S.WARNING)
    def error(self, text): self.set(f"✖  {text}", S.DANGER)
    def spin(self, text):  self.set(f"◌  {text}", S.ACCENT)


# ══════════════════════════════════════════════════════════════════════════════
#  CAMPO DE ENTRADA CON FOCUS RING
# ══════════════════════════════════════════════════════════════════════════════

class FocusField(tk.Frame):
    """Entry dentro de un marco con borde sutil que se ilumina al enfocar.

    Soporta un icono a la izquierda y un placeholder que desaparece al escribir.
    Accede al texto con `.value` / `.value = ...` o a la StringVar con `.var`.
    """
    def __init__(self, parent, *, textvariable=None, font=None, icon=None,
                 placeholder=None, mono=False):
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

    # ── Focus ring ────────────────────────────────────────────────────────────
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
        self._sb = tk.Scrollbar(self, orient="vertical", command=self.canvas.yview,
                                bg=S.BORDER, troughcolor=bg, bd=0,
                                activebackground=S.TEXT_DIM, relief="flat", width=10,
                                highlightthickness=0)
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
