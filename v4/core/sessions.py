"""
core/sessions.py — Modelo de datos y carga de sesiones de Claude Code.

Lee los ficheros `.jsonl` de ~/.claude/projects, los convierte en objetos
`Session`, replica la deduplicación del panel "Recents" de Claude Code y los
agrupa por proyecto en objetos `Project` para el sidebar.

No depende de tkinter ni de exporter: pura lógica de datos.
"""
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from core.utils import (
    decode_project_path, short_project_name, color_for_project,
)


# ══════════════════════════════════════════════════════════════════════════════
#  MODELO
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class Session:
    """Una conversación de Claude Code lista para mostrar y exportar."""
    path: Path
    session_id: str
    message_count: int
    first_ts: Optional[str]
    last_ts: Optional[str]
    first_user_msg: str
    title: str
    cwd: str
    raw_messages: list = field(repr=False, default_factory=list)
    project: str = ""          # nombre corto de la carpeta del proyecto
    project_full: str = ""     # ruta completa (para tooltip / dedup)

    @property
    def display_name(self) -> str:
        """Lo que se muestra como título de la sesión."""
        return self.title or self.first_user_msg or "(untitled)"

    @property
    def chip_colors(self):
        """(fg, bg) estable para el chip del proyecto."""
        return color_for_project(self.project_full or self.project)


@dataclass
class Project:
    """Agrupación de sesiones que comparten la misma ruta de proyecto."""
    name: str
    full_path: str
    sessions: List[Session] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.sessions)

    @property
    def last_ts(self) -> str:
        return max((s.last_ts or "" for s in self.sessions), default="")

    @property
    def chip_colors(self):
        return color_for_project(self.full_path or self.name)


# ══════════════════════════════════════════════════════════════════════════════
#  CARGA DE UN .jsonl
# ══════════════════════════════════════════════════════════════════════════════

def load_session_metadata(jsonl_path: Path) -> Optional[Session]:
    """Lee un `.jsonl` y extrae metadatos + mensajes crudos. None si está vacío."""
    messages, first_ts, last_ts, first_user_msg = [], None, None, ""
    ai_title, cwd = "", ""
    try:
        with open(jsonl_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                messages.append(obj)

                ts = obj.get("timestamp")
                if ts:
                    if first_ts is None:
                        first_ts = ts
                    last_ts = ts

                # Título real que Claude Code muestra en "Recents"
                if not ai_title and obj.get("type") == "ai-title":
                    ai_title = (obj.get("aiTitle") or "").strip()
                # Ruta real del proyecto (más fiable que el nombre de carpeta)
                if not cwd and obj.get("cwd"):
                    cwd = obj.get("cwd")

                # Primer mensaje de usuario (preview / clave de dedup)
                if not first_user_msg:
                    role    = obj.get("type") or obj.get("role", "")
                    content = obj.get("message", {}) if isinstance(obj.get("message"), dict) else {}
                    if role == "user" and content:
                        raw = content.get("content", "")
                        if isinstance(raw, list):
                            for block in raw:
                                if isinstance(block, dict) and block.get("type") == "text":
                                    first_user_msg = block.get("text", "")[:140]
                                    break
                        elif isinstance(raw, str):
                            first_user_msg = raw[:140]
    except Exception:
        return None

    if not messages:
        return None

    return Session(
        path=jsonl_path,
        session_id=jsonl_path.stem,
        message_count=len(messages),
        first_ts=first_ts,
        last_ts=last_ts,
        first_user_msg=first_user_msg or "(sin texto)",
        title=ai_title,
        cwd=cwd,
        raw_messages=messages,
    )


# ══════════════════════════════════════════════════════════════════════════════
#  RECOLECCIÓN + DEDUPLICACIÓN
# ══════════════════════════════════════════════════════════════════════════════

def gather_all_sessions(projects_dir: Path) -> List[Session]:
    """Recorre todos los proyectos, resuelve nombres reales, ordena por última
    actividad y deduplica conversaciones reiniciadas (igual que 'Recents')."""
    sessions: List[Session] = []
    for project_folder in sorted(projects_dir.iterdir()):
        if not project_folder.is_dir():
            continue
        fallback_label = decode_project_path(project_folder.name)
        for jsonl_file in sorted(project_folder.glob("*.jsonl")):
            s = load_session_metadata(jsonl_file)
            if not s:
                continue
            cwd = (s.cwd or "").strip()
            if cwd:
                s.project_full = cwd
                s.project      = Path(cwd).name
            else:
                s.project_full = fallback_label
                s.project      = short_project_name(fallback_label)
            sessions.append(s)

    sessions.sort(key=lambda s: s.last_ts or "", reverse=True)

    # Dedup: misma ruta de proyecto + mismo primer mensaje ⇒ misma conversación.
    # Conservamos la más reciente (ya está primera tras ordenar por last_ts desc).
    seen, deduped = set(), []
    for s in sessions:
        key = (s.project_full, (s.first_user_msg or "")[:80].strip().lower())
        if key not in seen:
            seen.add(key)
            deduped.append(s)
    return deduped


def group_by_project(sessions: List[Session]) -> List[Project]:
    """Agrupa sesiones por ruta de proyecto, ordenadas por actividad reciente."""
    by_path = {}
    for s in sessions:
        proj = by_path.get(s.project_full)
        if proj is None:
            proj = Project(name=s.project, full_path=s.project_full)
            by_path[s.project_full] = proj
        proj.sessions.append(s)
    projects = list(by_path.values())
    projects.sort(key=lambda p: p.last_ts, reverse=True)
    return projects
