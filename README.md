# Leave MCP Server

A beginner MCP server for HR leave management with one tool: `get_leave_balance`.

- **Stack:** Python 3.12 · official MCP Python SDK v2 (`mcp`) · Pydantic · `uv`
- **Client:** Claude Desktop (or the MCP Inspector for testing)
- **Concepts and interview notes:** see [MCP_NOTES.md](MCP_NOTES.md)

## Project structure

```
leave-mcp-server/
├── src/
│   └── main.py        # the MCP server (one tool)
├── pyproject.toml     # project info + dependencies
├── uv.lock            # exact pinned versions (commit this)
├── .python-version    # Python version for uv
├── MCP_NOTES.md       # concepts, explanations, interview Q&A
└── README.md
```

## Prerequisites

- [Claude Desktop](https://claude.ai/download)
- [uv](https://docs.astral.sh/uv/):
  ```bash
  powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
  ```
- Node.js (only needed for the MCP Inspector)

## Setup

```bash
uv sync
```

This installs the dependencies from `pyproject.toml` / `uv.lock` into `.venv`.

## Run

**Test in the browser (MCP Inspector):**

```bash
uv run mcp dev src/main.py
```

Toggle **Connect** → **Tools** → `get_leave_balance` → enter `E001` → run.

| Input | Expected |
|---|---|
| `E001` | `{"employee_id": "E001", "balance": 18}` |
| `E999` | Error: `Employee ID E999 not found.` |
| `abc` | Validation error (must match `^E\d{3}$`) |

**Connect to Claude Desktop:**

```bash
uv run mcp install src/main.py
```

Quit Claude Desktop from the system tray, reopen it, and ask: *"How many leaves are left for E001?"*

## Notes

- SDK **v2** import: `from mcp.server.mcpserver import MCPServer` (v1 tutorials use `from mcp.server.fastmcp import FastMCP`)
- Never use `print()` in the server. stdout carries the MCP messages. Use `print(..., file=sys.stderr)`.

## Troubleshooting

| Problem | Fix |
|---|---|
| Server "failed" in Claude → Settings → Developer | Check `%APPDATA%\Claude\logs\mcp-server-LeaveManager.log` |
| `spawn uv ENOENT` | Use uv's full path (`where uv`) as `"command"` in `%APPDATA%\Claude\claude_desktop_config.json` |
| `No module named 'mcp.server.fastmcp'` | You're on SDK v2: use the `MCPServer` import |
| `Expected a Python module at: src\leave_mcp_server\__init__.py` | Remove `[project.scripts]` and `[build-system]` from `pyproject.toml` |
| Tool not showing in Claude | Fully quit Claude from the tray and reopen |
