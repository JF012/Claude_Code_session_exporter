# Claude Code Session Exporter — v4

Rediseño completo de la app: **interfaz glassmorphism split-view** (sidebar de
proyectos · tabla central · vista previa en vivo) y **arquitectura modular** con
separación estricta entre lógica de negocio (`core/`) y UI (`ui/`).

Sigue siendo **tkinter + ttk puro, sin dependencias externas** — se ejecuta con el
Python estándar y se empaqueta como `.exe` autónomo.

---

## ▶ Ejecutar desde fuente

```bash
cd v4
pythonw main.py      # Windows, sin ventana de consola
# o, para ver logs:
python main.py
```

Requisitos: **Python 3.8+** (probado en 3.14). `tkinter` viene incluido en el
instalador estándar de Python. Sin `pip install` de nada.

---

## 🗂 Estructura del proyecto

```
v4/
├── main.py              # Punto de entrada: AppUserModelID + arranque
├── styles.py            # Paleta, fuentes, estilos ttk e icono embebido
├── widgets.py           # Primitivos UI: botón, status bar, campo con focus,
│                        #   contenedor scrollable, chip/badge, tooltip
├── core/                # Lógica de negocio (cero dependencias de tkinter)
│   ├── utils.py         #   color, rutas, formato, plataforma Windows, shortcut
│   ├── sessions.py      #   modelo Session/Project, carga .jsonl, dedup, agrupado
│   └── exporter.py      #   render a Markdown + escritura a disco
└── ui/                  # Componentes de interfaz
    ├── app.py           #   ventana principal: ensambla layout y orquesta estado
    ├── sidebar.py       #   sidebar izquierdo: marca + lista de proyectos
    ├── main_table.py    #   área central: buscador + tabla de sesiones custom
    ├── preview_panel.py #   sidebar derecho: preview Markdown en vivo
    └── toolbar.py       #   barra inferior: destino + acciones de exportación
```

### Principios de arquitectura

- **`core/` no importa nada de `ui/` ni de `tkinter`.** Es lógica pura y testeable:
  podrías reusarla desde una CLI o una web sin tocar una línea.
- **`ui/` no contiene lógica de negocio.** Cada componente recibe datos y
  *callbacks*; sólo `ui/app.py` conoce el estado completo y conecta las piezas.
- **`styles.py` es la única fuente de verdad visual.** Ningún módulo hardcodea un
  color: todo sale de la paleta. Cambia el tema entero editando un archivo.
- **El trabajo pesado corre en hilos** (escaneo y exportación) para no congelar la
  UI; los resultados vuelven al hilo principal con `after()`.

---

## ✨ Novedades de la v4 frente a la v3

| Área | v3 | v4 |
|:-----|:---|:---|
| Arquitectura | 1 archivo de 57 KB | paquete modular `core/` + `ui/` |
| Layout | header + tabla + toolbar | split-view de 3 paneles |
| Proyectos | mezclados en la tabla | sidebar dedicado con filtrado |
| Tabla | `ttk.Treeview` | filas custom: chip de color, título + preview, badge |
| Preview | — | **vista previa Markdown en tiempo real** |
| Exportar | una sesión | una sesión **o todas** las del filtro actual |
| Modelo de datos | `dict` | `dataclass` `Session` / `Project` |

Se mantienen **todas** las funciones de la v3: detección y deduplicación de
sesiones, nombres reales de proyecto/sesión, exportación a Markdown idéntica,
acceso directo en el Escritorio, icono embebido e identidad en la barra de tareas.

---

## 📦 Empaquetar como `.exe`

```bash
cd v4
pyinstaller ClaudeSessionExporter_v4.spec
# resultado: dist/ClaudeSessionExporter.exe (autónomo, sin consola)
```

El icono (`exporter_icon.ico`) se incrusta tanto en el `.exe` como en la ventana.
