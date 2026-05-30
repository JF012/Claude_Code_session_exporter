# 🟣 Claude Code Session Exporter

**Export any Claude Code session to clean, portable Markdown — in one click.**

A lightweight desktop GUI that scans your local Claude Code sessions, lets you pick one,
and exports the whole conversation to a tidy `.md` file. Perfect for handing context to a
**new** session so Claude can pick up exactly where you left off — or just for keeping a
readable archive of your work.

Built with **pure Python 3 + tkinter**. No external dependencies, no servers, no cloud —
everything runs locally and reads straight from your `~/.claude` folder.

---

## ✨ Features

### 🗂️ Smart Session Detection
- **Reads sessions locally** — Scans `~/.claude/projects/` automatically (Windows, macOS & Linux paths supported)
- **"Recents"-style view** — De-duplicates restarted/duplicate conversations so the list matches what Claude Code actually shows as active sessions
- **Short project names** — The *Proyecto* column shows just the project folder name (e.g. `Moodie`), with the full path available on hover
- **Live search & sort** — Instant filtering by project, first message or date, plus click-to-sort on every column

### 📤 Clean Markdown Export
- **One-click / double-click export** — Select a session and export, or just double-click a row
- **Readable formatting** — User turns, Claude replies, tool calls and system notes are laid out as clean Markdown sections
- **Configurable destination** — Defaults to `D:\Claude Code sessions`, changeable from the UI
- **Self-describing files** — Each export includes project, session ID, timestamps and message count in the header

### 🎨 Vibrant, Living UI
- **Animated gradient header** — A purple → blue (`#7c5cfc` → `#5b8dee`) gradient with a soft shimmer that drifts across the bar
- **Dynamic background** — Subtle diagonal gradient (`#0f1117` → `#1a1d27` → `#22263a`) behind the content, while the session table stays solid for full legibility
- **Gradient accent border** and **brighter button hovers** for a modern, polished feel
- **Embedded hexagon icon** — Shipped as base64 inside the script; applied to the window and the desktop shortcut

### ⚡ Zero-Friction Setup
- **No dependencies** — Only the Python standard library (`tkinter` ships with Python)
- **Desktop shortcut** — Offers to create a one-click launcher on your Desktop (Windows, via PowerShell)
- **No console window** — Runs as a `.pyw` so there's no black terminal on Windows

---

## 📱 Screens

| Session List | Export Result |
|:------------:|:-------------:|
| Animated header, searchable session table | Clean Markdown saved to your chosen folder |

> 📸 **Screenshot placeholder** — replace with a real capture:
>
> `![Claude Code Session Exporter](docs/screenshot.png)`

---

## 🚀 Getting Started

### Prerequisites
- **Python 3.x** — that's it. `tkinter` is included with the standard Python installer.
- *(Optional)* Windows, for the one-click desktop shortcut feature.

> 💡 No `pip install` step is required — there are no third-party packages.

### Installation

```bash
# Clone the repository
git clone https://github.com/JF012/Claude_Code_session_exporter.git

# Navigate to the project
cd Claude_Code_session_exporter
```

### Run

```bash
# Windows (no console window)
pythonw claude_exporter_gui-3.pyw

# Any platform (works too; shows a console on Windows)
python claude_exporter_gui-3.pyw
```

On first launch it offers to create a Desktop shortcut so you can open it with a single click.

---

## 🧠 How It Works

| Step | What happens |
|:-----|:-------------|
| 1. Scan | Finds `~/.claude/projects/` and reads every `*.jsonl` session file |
| 2. Parse | Extracts project, timestamps, message count and the first user message |
| 3. De-duplicate | Collapses restarted/duplicate conversations (same project + same opening message) — keeps the most recent |
| 4. Display | Lists active sessions in a sortable, searchable table |
| 5. Export | Renders the selected session to Markdown and saves it to your chosen folder |

### Where sessions are found

| OS | Path |
|:---|:-----|
| Windows | `%USERPROFILE%\.claude\projects\` (and `%APPDATA%\Claude\`) |
| macOS | `~/.claude/projects/` (and `~/Library/Application Support/Claude/`) |
| Linux | `~/.claude/projects/` |

---

## 🛠️ Tech Stack

| Technology | Purpose |
|:-----------|:--------|
| **Python 3** | Language / runtime |
| **tkinter + ttk** | GUI, custom widgets and Treeview table |
| **tkinter.Canvas** | Animated gradient header, shimmer and dynamic background |
| **PowerShell** *(Windows)* | Creates the Desktop `.lnk` shortcut |
| **base64** | Embedded application icon |

---

## 📄 License

Open source, available for educational and personal use.

---

<p align="center">
  Made with 🐍 Python by <a href="https://github.com/JF012">JF012</a>
</p>
