"""
ui/toolbar.py — Barra inferior (glass): destino + acciones de exportación.

Izquierda: etiqueta "Guardar en" + ruta editable + "Cambiar" / "Abrir".
Derecha: acción principal (Exportar a Markdown) separada de las secundarias
(Exportar todo, Crear acceso directo).

La toolbar no exporta nada: sólo recoge la ruta y dispara los callbacks.
"""
import tkinter as tk

import styles as S
from widgets import FocusField, RoundedButton


class Toolbar(tk.Frame):
    def __init__(self, parent, *, out_dir, on_change_dir, on_open_dir,
                 on_export, on_export_all, on_shortcut):
        super().__init__(parent, bg=S.BG_PANEL)
        row = tk.Frame(self, bg=S.BG_PANEL)
        row.pack(fill="x", padx=20, pady=13)

        # ── Izquierda: destino ────────────────────────────────────────────────
        tk.Label(row, text="Guardar en", bg=S.BG_PANEL, fg=S.TEXT_DIM,
                 font=S.font(9)).pack(side="left", padx=(0, 10))

        self.dir_var = tk.StringVar(value=str(out_dir))
        self._field = FocusField(row, textvariable=self.dir_var, mono=True)

        # ── Derecha: acciones ─────────────────────────────────────────────────
        self._btn_export = RoundedButton(row, "⬇   Exportar a Markdown", on_export,
                                         variant="primary", font_size=10)
        self._btn_export.pack(side="right")
        self._btn_export.set_enabled(False)

        RoundedButton(row, "⤓  Exportar todo", on_export_all,
                      variant="secondary", font_size=9).pack(side="right", padx=(0, 10))
        RoundedButton(row, "🔗  Acceso directo", on_shortcut,
                      variant="flat", font_size=9).pack(side="right", padx=(0, 10))

        # Acciones sobre la ruta (junto al campo)
        RoundedButton(row, "Abrir", on_open_dir,
                      variant="flat", font_size=9).pack(side="right", padx=(14, 8))
        RoundedButton(row, "Cambiar", on_change_dir,
                      variant="flat", font_size=9).pack(side="right")

        # El campo de ruta ocupa el centro
        self._field.pack(side="left", fill="x", expand=True, padx=(0, 16))

    # ── API ───────────────────────────────────────────────────────────────────
    @property
    def out_dir(self) -> str:
        return self.dir_var.get()

    @out_dir.setter
    def out_dir(self, value):
        self.dir_var.set(str(value))

    def set_export_enabled(self, enabled: bool):
        self._btn_export.set_enabled(enabled)

    def set_export_text(self, text):
        self._btn_export.set_text(text)
