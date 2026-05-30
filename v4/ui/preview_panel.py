"""
ui/preview_panel.py — Sidebar derecho: vista previa del Markdown.

Renderiza en tiempo real lo que se exportaría de la sesión seleccionada, con
formato real (títulos, citas, bloques de código, negritas e inline code) sobre
un Text de solo lectura. No es un parser Markdown completo: cubre justo lo que
produce exporter.session_to_markdown().
"""
import re
import tkinter as tk

import styles as S
from core.exporter import session_to_markdown

WIDTH = 366
MAX_CHARS = 16000          # corta previews enormes para mantener la fluidez


class PreviewPanel(tk.Frame):
    def __init__(self, parent):
        super().__init__(parent, bg=S.BG_GLASS, width=WIDTH)
        self.pack_propagate(False)

        # Cabecera
        head = tk.Frame(self, bg=S.BG_GLASS)
        head.pack(fill="x", padx=18, pady=(18, 10))
        tk.Label(head, text="◳", bg=S.BG_GLASS, fg=S.ACCENT_VIOLET,
                 font=S.font(13)).pack(side="left", padx=(0, 8))
        tk.Label(head, text="Vista previa de exportación", bg=S.BG_GLASS, fg=S.TEXT,
                 font=S.font(11, "bold")).pack(side="left")
        tk.Frame(self, bg=S.BORDER_SOFT, height=1).pack(fill="x", padx=16)

        # Texto
        body = tk.Frame(self, bg=S.BG_GLASS)
        body.pack(fill="both", expand=True, padx=(14, 6), pady=10)
        self._text = tk.Text(
            body, bg=S.BG_GLASS, fg=S.TEXT_SOFT, bd=0, relief="flat",
            highlightthickness=0, wrap="word", padx=8, pady=6,
            font=S.font(10), insertwidth=0, cursor="arrow", spacing1=1, spacing3=2,
        )
        sb = tk.Scrollbar(body, orient="vertical", command=self._text.yview,
                          bg=S.BORDER, troughcolor=S.BG_GLASS, bd=0,
                          activebackground=S.TEXT_DIM, relief="flat", width=10,
                          highlightthickness=0)
        self._text.configure(yscrollcommand=sb.set)
        self._text.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        self._configure_tags()
        self._text.config(state="disabled")
        self.show_placeholder()

    # ── Tags de formato ───────────────────────────────────────────────────────
    def _configure_tags(self):
        t = self._text
        t.tag_configure("h1", font=S.font(15, "bold"), foreground=S.TEXT,
                        spacing1=6, spacing3=8)
        t.tag_configure("h2", font=S.font(11, "bold"), foreground=S.ACCENT_SOFT,
                        spacing1=10, spacing3=4)
        t.tag_configure("quote", font=S.font(9), foreground=S.TEXT_MUTE,
                        lmargin1=10, lmargin2=10, spacing1=1)
        t.tag_configure("code", font=S.mono(9), foreground="#a5b4fc",
                        background=S.BG_DEEP, lmargin1=12, lmargin2=12,
                        spacing1=0, spacing3=0)
        t.tag_configure("hr", foreground=S.BORDER, spacing1=4, spacing3=8)
        t.tag_configure("bold", font=S.font(10, "bold"), foreground=S.TEXT)
        t.tag_configure("icode", font=S.mono(9), foreground=S.ACCENT_VIOLET,
                        background=S.BG_DEEP)
        t.tag_configure("normal", foreground=S.TEXT_SOFT, spacing1=1, spacing3=1)
        t.tag_configure("muted", foreground=S.TEXT_DIM, font=S.font(9))

    # ── API pública ───────────────────────────────────────────────────────────
    def show_placeholder(self):
        self._set_readonly(lambda: self._text.insert(
            "1.0",
            "\n\n   Selecciona una sesión para ver\n"
            "   aquí su exportación en Markdown.\n",
            "muted"))

    def show_session(self, session):
        md = session_to_markdown(session)
        truncated = len(md) > MAX_CHARS
        if truncated:
            md = md[:MAX_CHARS]
        self._set_readonly(lambda: self._render(md, truncated))
        self._text.yview_moveto(0.0)

    # ── Render interno ────────────────────────────────────────────────────────
    def _set_readonly(self, fn):
        self._text.config(state="normal")
        self._text.delete("1.0", "end")
        fn()
        self._text.config(state="disabled")

    def _render(self, md, truncated):
        in_code = False
        for raw in md.split("\n"):
            line = raw.rstrip("\n")

            if line.startswith("```"):
                in_code = not in_code
                continue
            if in_code:
                self._text.insert("end", (line or " ") + "\n", "code")
                continue

            if line.startswith("# "):
                self._text.insert("end", line[2:] + "\n", "h1")
            elif line.startswith("## "):
                self._text.insert("end", line[3:] + "\n", "h2")
            elif line.strip() == "---":
                self._text.insert("end", "─" * 40 + "\n", "hr")
            elif line.startswith("> "):
                self._insert_inline(line[2:], base="quote")
            elif line.strip() == "":
                self._text.insert("end", "\n", "normal")
            else:
                self._insert_inline(line, base="normal")

        if truncated:
            self._text.insert("end", "\n\n", "normal")
            self._text.insert("end", "… vista previa truncada (el .md completo se "
                                     "exporta entero)\n", "muted")

    def _insert_inline(self, text, *, base):
        """Inserta una línea aplicando **negrita** y `code` inline."""
        pos = 0
        for m in re.finditer(r"\*\*(.+?)\*\*|`([^`]+)`", text):
            if m.start() > pos:
                self._text.insert("end", text[pos:m.start()], base)
            if m.group(1) is not None:
                self._text.insert("end", m.group(1), "bold")
            else:
                self._text.insert("end", m.group(2), "icode")
            pos = m.end()
        if pos < len(text):
            self._text.insert("end", text[pos:], base)
        self._text.insert("end", "\n", base)
