# Leave MCP Server

A beginner MCP (Model Context Protocol) server for HR leave management, plus my revision notes on MCP for interviews.

- **Use case:** An HR manager asks an AI assistant in plain English, "How many leaves are left for E001?", and the assistant answers from the company's employee data.
- **Server:** Python + `MCPServer` (official MCP Python SDK v2; called `FastMCP` in v1), managed with `uv`
- **Client:** Claude Desktop
- **Tools:** 1 (`get_leave_balance`)

---

## Table of contents

1. [MCP in one line](#1-mcp-in-one-line)
2. [The basic problem: an LLM has no hands](#2-the-basic-problem-an-llm-has-no-hands)
3. [Tool calling (function calling)](#3-tool-calling-function-calling)
4. [Why "standard"? The plug and socket analogy](#4-why-standard-the-plug-and-socket-analogy)
5. [Host vs MCP client vs MCP server](#5-host-vs-mcp-client-vs-mcp-server)
6. [What actually goes over the wire (JSON-RPC)](#6-what-actually-goes-over-the-wire-json-rpc)
7. [Tools, resources, prompts](#7-tools-resources-prompts)
8. [Transports: stdio vs streamable HTTP](#8-transports-stdio-vs-streamable-http)
9. [Without MCP vs with MCP](#9-without-mcp-vs-with-mcp)
10. [MCP vs microservices / REST APIs](#10-mcp-vs-microservices--rest-apis)
11. [Security](#11-security)
12. [Which apps can talk to an MCP server?](#12-which-apps-can-talk-to-an-mcp-server)
13. [uv: the Python package manager](#13-uv-the-python-package-manager)
14. [pyproject.toml vs requirements.txt](#14-pyprojecttoml-vs-requirementstxt)
15. [What `uv run mcp install` does](#15-what-uv-run-mcp-install-does)
16. [Implementation: step by step](#16-implementation-step-by-step)
17. [Troubleshooting](#17-troubleshooting)
18. [Interview quick revision (Q&A)](#18-interview-quick-revision-qa)

---

## 1. MCP in one line

> **MCP is an open standard (by Anthropic, Nov 2024) for how AI apps discover and call external tools and data.** It's often called "USB-C for AI": build a tool once and plug it into any AI app.

---

## 2. The basic problem: an LLM has no hands

- An LLM (Claude, Gemini, GPT) only knows what it learned during training.
- It **can't** see my company database, files, Slack, GitHub and so on.
- Ask it "How many leaves does E001 have?" and it can only guess.
- To answer, it needs a way to **call code** that reads the real data.

**LLM = brain. Tools = hands. MCP = the standard way to attach hands to any brain.**

---

## 3. Tool calling (function calling)

The mechanism underneath MCP:

```
1. App tells the LLM:   "There is a function get_leave_balance(employee_id)"
2. User asks:           "How many leaves for E001?"
3. LLM replies:         "Please call get_leave_balance('E001')"   <- the LLM does NOT run it
4. App runs it:         -> "E001 has 18 leave days remaining."
5. LLM answers user:    "E001 has 18 days of leave left."
```

### Why the docstring matters so much

The LLM **never sees the Python code**. It only sees:

- the function **name**: `get_leave_balance`
- the **parameters and types**: `employee_id: str`
- the **docstring**: "Check how many leave days are left for an employee…"

The docstring is the **instruction manual for the AI**. In the video, the LLM turned "4th July" into `2025-07-04` because the docstring said the format is `YYYY-MM-DD`. A vague docstring leads to wrong or missed tool calls.

---

## 4. Why "standard"? The plug and socket analogy

A fan works in **any** socket (home, office, hotel) because every manufacturer agreed on one plug shape. That agreement is a **standard**.

```
REAL LIFE                                   MCP WORLD

Fan    ─┐                 ┌─ Your home      Leave server    ─┐                ┌─ Claude Desktop
TV     ─┼─ Standard plug ─┼─ Office         GitHub server   ─┼─ MCP protocol ─┼─ Cursor / VS Code
Mixer  ─┘   & socket      └─ Hotel          Database server ─┘  (same JSON)   └─ My Node app

Appliance   = MCP server
Socket      = MCP client (built into the app)
Plug shape  = MCP protocol
```

"Standard" means:

- **Same message names** for everyone: `initialize`, `tools/list`, `tools/call`, …
- **Same JSON payload and response structure** (JSON-RPC 2.0)
- So **one server works with many clients**, and **one client works with many servers**
- Main benefit: **reusability**. Write the tool once and use it everywhere.

I never hand-write this JSON. The SDK (`MCPServer`, formerly `FastMCP`) generates it from my function signature and docstring.

---

## 5. Host vs MCP client vs MCP server

```
┌──────────────────── Claude Desktop (HOST) ────────────────────┐
│                                                               │
│  User: "How many leaves for E001?"                            │
│        │                                                      │
│        ▼                                                      │
│   ┌─────────┐   "call get_leave_balance"   ┌─────────────┐    │
│   │   LLM   │ ───────────────────────────► │ MCP CLIENT  │    │
│   │ (brain) │ ◄─────────────────────────── │ (waiter)    │    │
│   └─────────┘          result              └──────┬──────┘    │
└───────────────────────────────────────────────────┼───────────┘
                                                    │ MCP protocol (JSON-RPC)
                                                    ▼
                                           ┌──────────────────┐
                                           │   MCP SERVER     │  <- this project
                                           │   (kitchen)      │
                                           │ get_leave_balance│
                                           └────────┬─────────┘
                                                    ▼
                                              Employee DB
```

| | MCP server | MCP client |
|---|---|---|
| What | Program that **exposes** tools/data | Connector inside an AI app that **uses** servers |
| Who writes it | Whoever owns the data (me, GitHub, Slack…) | The AI app maker (Anthropic, Cursor…), or me for my own app |
| Job | "Here are my tools. Call them and I'll do the work." | "What tools do you have? The LLM wants this one, here are the args." |
| Knows about the LLM? | **No.** It only receives a `tools/call` request. | **Yes.** It sits between the LLM and the servers. |
| In this project | `src/main.py` | Claude Desktop |

**Host** = the full app the user sees (Claude Desktop). It contains the LLM and one MCP client per connected server.

### Restaurant analogy: "the server doesn't know about the LLM"

- **Customer** = user. **LLM** = decides what to order.
- **MCP client** = the waiter. It shows the menu (tool list), takes the order, carries the slip to the kitchen and brings the food back.
- **MCP server** = the kitchen. It never meets the customer. It only sees the slip:
  `tools/call  name: "get_leave_balance"  arguments: { employee_id: "E001" }`
- It doesn't know the user's English question, or whether Claude, Gemini or GPT is on the other side.
- **That's why the same server works with any LLM.**

---

## 6. What actually goes over the wire (JSON-RPC)

**Client → server: "What tools do you have?"**
```json
{ "jsonrpc": "2.0", "id": 1, "method": "tools/list" }
```

**Server → client**
```json
{
  "jsonrpc": "2.0", "id": 1,
  "result": {
    "tools": [{
      "name": "get_leave_balance",
      "description": "Check how many leave days are left for an employee.",
      "inputSchema": {
        "type": "object",
        "properties": { "employee_id": { "type": "string" } },
        "required": ["employee_id"]
      }
    }]
  }
}
```

**Client → server: call the tool (after the LLM decides to)**
```json
{
  "jsonrpc": "2.0", "id": 2, "method": "tools/call",
  "params": { "name": "get_leave_balance", "arguments": { "employee_id": "E001" } }
}
```

**Server → client**
```json
{
  "jsonrpc": "2.0", "id": 2,
  "result": { "content": [{ "type": "text", "text": "E001 has 18 leave days remaining." }] }
}
```

Lifecycle: `initialize` (handshake, capabilities) → `tools/list` → `tools/call` (as many times as needed).

---

## 7. Tools, resources, prompts

An MCP server can expose 3 kinds of things:

| Primitive | What it is | Who controls it | Example |
|---|---|---|---|
| **Tools** | Functions the LLM can call (can have side effects) | The **model** decides when | `get_leave_balance`, `apply_leave` |
| **Resources** | Read-only data, like files (identified by a URI) | The **app/user** attaches them | `greeting://{name}`, `file:///policy.pdf` |
| **Prompts** | Reusable prompt templates | The **user** picks them | "Summarize leave report for {employee}" |

This project uses **tools** only.

---

## 8. Transports: stdio vs streamable HTTP

| | stdio | Streamable HTTP |
|---|---|---|
| How | Host starts the server as a **child process** and talks over stdin/stdout | Server runs as a web service; clients connect over the network |
| Where | Local machine only | Remote / cloud |
| Network port | None | Yes |
| Auth | Not needed (local) | OAuth 2.1 per the MCP spec |
| Use | Personal or dev tools, Claude Desktop | Company-wide shared servers, production |

This project uses **stdio**: Claude Desktop runs `uv run ... main.py` itself.

(Older remote transport: HTTP + SSE. Now replaced by streamable HTTP.)

---

## 9. Without MCP vs with MCP

### Without MCP: M × N problem

```
Internal chatbot (OpenAI) ── custom glue #1 ──► Leave DB
Slack bot (Gemini)        ── custom glue #2 ──► Leave DB
VS Code (Claude)          ── custom glue #3 ──► Leave DB
```

- Each LLM provider has its **own tool-calling format** (OpenAI, Gemini and Anthropic schemas differ).
- Rewrite the tool definitions, the call loop and the integration for **every app × every data source**.
- M apps × N data sources = **M × N integrations**.

### With MCP: M + N

```
Internal chatbot ─┐                 ┌─► Leave MCP server  ──► Leave DB
Slack bot        ─┼── MCP protocol ─┼─► GitHub MCP server
VS Code / Cursor ─┤                 └─► Jira MCP server
Claude Desktop   ─┘
```

- Write the server **once**; every MCP client can use it.
- **M + N** integrations instead of M × N.
- Thousands of ready-made servers exist (GitHub, Slack, Postgres, Google Drive, filesystem…).

### Benefits seen in the demo

1. **No UI needed.** The HR manager just chats in plain English.
2. **Natural language → structured call.** "4th July" became `2025-07-04`, and typos were handled.
3. **Context memory.** "Same person" was understood as E001.
4. **Reusable.** The same server works in Claude Desktop, Cursor, or my own chatbot.
5. **Separation of concerns.** The data team owns the server; the AI app team owns the client.
6. **Dynamic discovery.** The client asks `tools/list` at runtime. Add a tool and it shows up automatically with no client code change.

---

## 10. MCP vs microservices / REST APIs

**They aren't competitors. They're different layers.**

| | Microservice / REST API | MCP server |
|---|---|---|
| Caller | Other programs written by developers | An **LLM** deciding at runtime |
| Discovery | Developer reads Swagger docs and hardcodes `POST /leaves` | Client asks `tools/list` at runtime and gets names, descriptions and schemas |
| Descriptions are for | Humans | The AI (docstrings) |
| Contract | Every API is different (URLs, auth, formats) | One standard protocol for all servers |
| Purpose | Building backend systems | Giving AI agents hands |

**In real companies, MCP wraps existing services:**

```
LLM ──► MCP client ──► Leave MCP server ──► existing Leave microservice (REST) ──► DB
```

MCP is the **AI-friendly front door / adapter layer** over existing APIs. Don't rewrite the microservice; write a thin MCP server whose tool calls the REST API.

**Why not let the LLM call REST directly?** It would need to know every API's URL, auth, headers and format. REST APIs don't describe themselves in an LLM-discoverable way. And you'd be back to custom glue per API × per LLM.

---

## 11. Security

**MCP is mainly about standardization, not security.** But it gives some safety by design:

1. **Least privilege.** The LLM can only call the tools I expose. It can't run arbitrary SQL or read the whole DB.
2. **Human in the loop.** The host asks the user ("Allow for this chat?") before running a tool.
3. **stdio is local.** No open port, so nothing is reachable from the internet.
4. **Remote auth.** Streamable HTTP servers use **OAuth 2.1** per the spec.

**Risks to mention in an interview:**

- **Malicious or untrusted servers.** A server is just code running on my machine. Only install trusted ones (like npm packages).
- **Prompt injection.** Data returned by a tool (an email, a web page) can contain text that tricks the LLM into calling other tools.
- **Tool poisoning.** A malicious server hides instructions in its tool descriptions.
- **Over-permissive tools.** e.g. a `run_sql(query)` tool hands the LLM the whole DB. Prefer narrow tools.
- **Secrets.** Keep API keys in env vars or config, not in tool outputs.

---

## 12. Which apps can talk to an MCP server?

**Only apps that contain MCP client code**, just as only houses with sockets can power a fan.

| App | MCP client? |
|---|---|
| Claude Desktop, Claude Code, Cursor, VS Code Copilot, Windsurf | Built in |
| ChatGPT | Via connectors |
| My own Node.js + Gemini app | Only if I add `@modelcontextprotocol/sdk` |
| Normal website / Postman | No |

### Making my own Node app an MCP client (for later)

```js
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";

const client = new Client({ name: "atl-hr-bot", version: "1.0.0" });
await client.connect(
  new StdioClientTransport({ command: "uv", args: ["run", "src/main.py"] })
);

const { tools } = await client.listTools();      // give these to Gemini as functionDeclarations
const result = await client.callTool({            // when Gemini asks for a tool
  name: "get_leave_balance",
  arguments: { employee_id: "E001" },
});
```

---

## 13. uv: the Python package manager

**uv** is a fast Python package and project manager written in Rust, by Astral. It replaces `pip`, `venv`, `pip-tools`, `poetry` and `pyenv` in one tool. **Think of it as npm for Python.**

| Node.js | Python with uv |
|---|---|
| `npm init` | `uv init <name>` |
| `package.json` | `pyproject.toml` |
| `package-lock.json` | `uv.lock` |
| `node_modules/` | `.venv/` |
| `npm install` | `uv sync` |
| `npm install express` | `uv add mcp` |
| `npm uninstall x` | `uv remove x` |
| `npx something` / `npm run` | `uv run something` |
| `.nvmrc` | `.python-version` |

---

## 14. pyproject.toml vs requirements.txt

`pyproject.toml` ≈ **`package.json`**. It's a superset of `requirements.txt`.

| | `requirements.txt` | `pyproject.toml` |
|---|---|---|
| Lists dependencies | Yes | Yes (`dependencies = [...]`) |
| Project name, version, authors | No | Yes |
| Required Python version | No | Yes (`requires-python`) |
| Tool config (linters, build system, scripts) | No | Yes |
| Auto-updated | No (manual or `pip freeze`) | Yes, by `uv add` |
| Status | Old convention | Official modern standard (PEP 621) |

- **`uv.lock`** ≈ `package-lock.json`. It pins the exact versions of everything, including sub-dependencies. Don't edit it by hand. Commit it.
- Someone cloning the repo runs **`uv sync`** to get the identical environment.

---

## 15. What `uv run mcp install` does

Claude Desktop doesn't know my server exists. Someone must tell it **"there's a server called LeaveManager, and here's the command to start it."**

That information lives in Claude Desktop's config:
`%APPDATA%\Claude\claude_desktop_config.json`

`uv run mcp install src/main.py` **just writes this entry for me**:

```json
{
  "mcpServers": {
    "LeaveManager": {
      "command": "uv",
      "args": ["run", "--with", "mcp[cli]", "mcp", "run", "D:\\Rohith\\Project\\leave-mcp-server\\src\\main.py"]
    }
  }
}
```

On every launch, Claude Desktop:

1. Reads the config.
2. Runs that command, which starts my Python server as a child process (stdio).
3. Sends `initialize` and then `tools/list`, and shows my tools in the tools icon.

- **Why `uv` in the command?** It guarantees the right Python and the `mcp` package are present every time, independent of whatever Python is installed globally.
- I could **skip the command and paste the JSON by hand**. The result is the same.
- `mcp install` is **Claude Desktop only**. Cursor and VS Code have their own `mcp.json` where I add a similar entry manually.
- **Developer mode** in Claude Desktop unlocks **Settings → Developer**, where I can see server status and click "Edit Config".

---

## 16. Implementation: step by step

### Prerequisites

1. **Claude Desktop**: install from claude.ai/download and log in.
2. **uv** (PowerShell):
   ```bash
   powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
   ```
   Reopen the terminal and check with `uv --version`.

### Step 1: Create the project (already done)

```bash
uv init leave-mcp-server
cd leave-mcp-server
```

> Note: this repo was first created with `uv init --package` (layout `src/leave_mcp_server/__init__.py`, plus `[project.scripts]` and `[build-system]` in `pyproject.toml`). I removed the package folder **and those two blocks**. Otherwise `uv add` fails with `Expected a Python module at: src\leave_mcp_server\__init__.py`. My server file is now just `src/main.py`.

### Step 2: Add the MCP SDK

```bash
uv add "mcp[cli]"
```

This updates `pyproject.toml` → `dependencies` and creates `.venv/` and `uv.lock`.

### Step 3: Create `src/main.py`

> **SDK version matters.** `uv add "mcp[cli]"` installed **mcp 2.x**. In v2, `FastMCP` was **renamed to `MCPServer`**:
> - v1 (most tutorials and the video): `from mcp.server.fastmcp import FastMCP`
> - v2 (installed here): `from mcp.server.mcpserver import MCPServer`
>
> Using the v1 import on v2 gives `ModuleNotFoundError: No module named 'mcp.server.fastmcp'`. Either use the v2 import (below) or pin `uv add "mcp[cli]<2"` to follow v1 tutorials as written.

```python
from mcp.server.mcpserver import MCPServer

# Mock database (in real life: a DB or REST API call)
employee_leaves = {
    "E001": {"balance": 18, "history": ["2024-12-25", "2025-01-01"]},
    "E002": {"balance": 20, "history": []},
}

# Create the MCP server
mcp = MCPServer("LeaveManager")


@mcp.tool()
def get_leave_balance(employee_id: str) -> str:
    """Check how many leave days are left for an employee.

    Args:
        employee_id: Employee ID like "E001" or "E002".
    """
    data = employee_leaves.get(employee_id)
    if data:
        return f"{employee_id} has {data['balance']} leave days remaining."
    return f"Employee ID {employee_id} not found."


if __name__ == "__main__":
    mcp.run()  # default transport = stdio
```

What each part does:

- `MCPServer("LeaveManager")` creates the server (it was called `FastMCP` in v1).
- `@mcp.tool()` registers the function, so it appears in `tools/list`.
- Type hints (`employee_id: str`) become the tool's `inputSchema`.
- The docstring becomes the tool's `description`, which the LLM reads.
- `mcp.run()` starts listening on stdio.

### Step 4: Test without Claude (MCP Inspector)

```bash
uv run mcp dev src/main.py
```

This opens the Inspector in the browser (it needs Node). Click **Connect** → **Tools** → **List Tools** → `get_leave_balance` → enter `E001` → **Run**. Expect "E001 has 18 leave days remaining."
It's like Postman for MCP. Press Ctrl+C to stop.

### Step 5: Register with Claude Desktop

```bash
uv run mcp install src/main.py
```

### Step 6: Restart Claude Desktop fully

Quit it from the **system tray**; closing the window isn't enough. Reopen it.
Check **Settings → Developer**: `LeaveManager` should show as running.

### Step 7: Try it

> How many leaves are left for employee E001?

Claude asks permission. Click **Allow**, and the answer is 18 days.

---

## 17. Troubleshooting

| Problem | Fix |
|---|---|
| Server shows "failed" in Settings → Developer | Check the log: `%APPDATA%\Claude\logs\mcp-server-LeaveManager.log` |
| `spawn uv ENOENT` | Claude can't find uv. Run `where uv` and put the full path (e.g. `C:\\Users\\rohit\\.local\\bin\\uv.exe`) as `"command"` in the config |
| `typer` / `TypeError` on install | `uv add --upgrade typer`, then rerun `uv run mcp install src/main.py` |
| Tool not showing | Fully quit Claude from the tray and reopen |
| `print()` breaks the server | With stdio, stdout is the protocol channel. Never `print()` in the server; log to stderr instead (`print(..., file=sys.stderr)`) |

---

## 18. Interview quick revision (Q&A)

**Q: What is MCP?**
An open protocol by Anthropic (Nov 2024) that standardizes how AI applications connect to external tools, data and prompts. It's "USB-C for AI".

**Q: What problem does it solve?**
The M × N integration problem. Without it, every AI app needs custom glue for every data source and every LLM provider's tool format. With MCP it's M + N: build a server once and use it from any MCP client.

**Q: Host vs client vs server?**
- Host = the user-facing AI app (Claude Desktop).
- Client = the connector inside the host. It keeps a 1:1 connection with one server.
- Server = the program exposing tools, resources and prompts.

**Q: Does the MCP server talk to the LLM?**
No. The server only receives JSON-RPC requests like `tools/call` with a name and arguments. It's LLM-agnostic. The client and host handle the LLM.

**Q: What protocol format does MCP use?**
JSON-RPC 2.0. Key methods: `initialize`, `tools/list`, `tools/call`, `resources/list`, `resources/read`, `prompts/list`, `prompts/get`.

**Q: Three primitives?**
Tools (model-controlled functions), resources (app-controlled read-only data), prompts (user-controlled templates).

**Q: Transports?**
stdio (local child process) and streamable HTTP (remote, with OAuth). SSE is the older remote transport.

**Q: How does the LLM know which tool to call and with what arguments?**
The client sends the LLM each tool's name, description (from the docstring) and input JSON schema (from the type hints). The LLM maps the user's question to a tool and fills in the arguments.

**Q: Why is the docstring important?**
It's the only documentation the LLM sees. It drives tool selection and argument formatting (e.g. date format `YYYY-MM-DD`).

**Q: MCP vs REST APIs / microservices?**
Different layers. REST is for programs written by developers who read the docs. MCP is for LLMs that discover tools at runtime. MCP servers often wrap existing REST microservices as an AI-friendly adapter layer.

**Q: MCP vs plain function calling?**
Function calling is the LLM capability ("call this function"). MCP is the standard for packaging, discovering and connecting those functions across apps, and it's provider-agnostic. MCP uses function calling underneath.

**Q: Security concerns?**
Untrusted servers run code on your machine; prompt injection through tool outputs; tool poisoning through descriptions; over-broad tools. Mitigations: least-privilege tools, human approval, trusted servers only, OAuth for remote servers, and keeping secrets out of outputs.

**Q: What is uv?**
A fast Rust-based Python package and project manager by Astral, like npm for Python. `pyproject.toml` ≈ `package.json`, `uv.lock` ≈ `package-lock.json`, `.venv` ≈ `node_modules`.

**Q: What does `uv run mcp install src/main.py` do?**
It adds the server's start command to `claude_desktop_config.json`, so Claude Desktop launches the server (stdio) on startup and discovers its tools.

**Q: Can multiple clients use one MCP server?**
Yes. That's the point of the standard. With stdio, each host starts its own process. With streamable HTTP, one deployed server serves many clients.

**Q: Can any app talk to an MCP server?**
Only apps that implement an MCP client (Claude Desktop, Cursor, VS Code, ChatGPT connectors, or a custom app using the MCP SDK).

**Q: Why can't you `print()` in a stdio MCP server?**
stdout carries the JSON-RPC messages. Extra output corrupts the protocol. Log to stderr instead.
