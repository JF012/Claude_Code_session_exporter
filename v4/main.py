"""
Claude Code Session Exporter — v4
=================================
Punto de entrada. Ejecutar sin consola en Windows con:

    pythonw main.py

Fija la identidad de la app en Windows (para el icono de la barra de tareas)
y arranca la ventana principal. Toda la lógica vive en los paquetes `core/`
(negocio) y `ui/` (interfaz); `styles.py` y `widgets.py` aportan la capa visual.
"""
from core.utils import set_app_user_model_id
from ui.app import App


def main():
    set_app_user_model_id()
    App().mainloop()


if __name__ == "__main__":
    main()
