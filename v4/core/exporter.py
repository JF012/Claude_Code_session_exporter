"""
core/exporter.py — Render de una sesión a Markdown y escritura a disco.

`session_to_markdown` produce exactamente el mismo formato que la v3 (turnos de
usuario, respuestas de Claude, llamadas a herramientas y notas de sistema) para
que el panel de preview y el fichero exportado coincidan al 100 %.
"""
import json
from datetime import datetime
from pathlib import Path

from core.utils import format_ts
from core.sessions import Session


# ══════════════════════════════════════════════════════════════════════════════
#  EXTRACCIÓN DE TEXTO DE LOS BLOQUES DE CONTENIDO
# ══════════════════════════════════════════════════════════════════════════════

def extract_text(content) -> str:
    """Convierte el `content` de un mensaje (str | list | dict) en texto Markdown.
    Las llamadas y resultados de herramientas se envuelven en bloques de código."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if not isinstance(block, dict):
                continue
            btype = block.get("type", "")
            if btype == "text":
                parts.append(block.get("text", ""))
            elif btype == "tool_use":
                name = block.get("name", "tool")
                inp  = block.get("input", {})
                parts.append(
                    f"```tool:{name}\n"
                    f"{json.dumps(inp, indent=2, ensure_ascii=False)}\n```"
                )
            elif btype == "tool_result":
                res = block.get("content", "")
                if isinstance(res, list):
                    res = "\n".join(b.get("text", "") for b in res if isinstance(b, dict))
                parts.append(f"```tool_result\n{res}\n```")
        return "\n\n".join(p for p in parts if p)
    if isinstance(content, dict):
        return extract_text(content.get("content", ""))
    return ""


# ══════════════════════════════════════════════════════════════════════════════
#  RENDER A MARKDOWN
# ══════════════════════════════════════════════════════════════════════════════

def session_to_markdown(session: Session) -> str:
    """Documento Markdown completo de una sesión (cabecera + turnos + pie)."""
    lines = [
        "# Sesión Claude Code",
        "",
        f"> **Sesión:** {session.display_name or '—'}  ",
        f"> **Proyecto:** `{session.project}`  ",
        f"> **Session ID:** `{session.session_id}`  ",
        f"> **Inicio:** {format_ts(session.first_ts)}  ",
        f"> **Última actividad:** {format_ts(session.last_ts)}  ",
        f"> **Mensajes totales:** {session.message_count}",
        "",
        "---",
        "",
    ]
    turn = 0
    for obj in session.raw_messages:
        role = obj.get("type") or obj.get("role", "")
        msg  = obj.get("message", obj) if isinstance(obj.get("message"), dict) else obj
        text = extract_text(msg.get("content", "")).strip() if isinstance(msg, dict) else ""

        if role == "user":
            if not text:
                continue
            turn += 1
            lines += [f"## 🧑 Usuario — turno {turn}", "", text, "", "---", ""]
        elif role == "assistant":
            if not text:
                continue
            lines += ["## 🤖 Claude", "", text, "", "---", ""]
        elif role == "system" and text:
            lines += ["## ⚙️ System", "", f"> {text}", "", "---", ""]

    lines.append(
        f"*Exportado el {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} "
        f"con Claude Code Session Exporter*"
    )
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
#  ESCRITURA A DISCO
# ══════════════════════════════════════════════════════════════════════════════

def build_filename(session: Session) -> str:
    """Nombre de fichero determinista: claude_session_<fecha>_<sid8>.md"""
    ts_part  = format_ts(session.last_ts).replace(":", "-").replace(" ", "_").strip()
    sid_part = session.session_id[:8]
    return f"claude_session_{ts_part}_{sid_part}.md"


def export_session(session: Session, out_dir: Path) -> Path:
    """Renderiza y escribe una sesión en `out_dir`. Devuelve el Path del .md."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / build_filename(session)
    out_path.write_text(session_to_markdown(session), encoding="utf-8")
    return out_path


def has_readable_turns(markdown: str) -> bool:
    """True si el Markdown contiene al menos un turno de usuario o de Claude."""
    return ("## 🧑" in markdown) or ("## 🤖" in markdown)
