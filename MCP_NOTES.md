# MCP Notes: Concepts and Interview Revision

My learning notes from building the [Leave MCP Server](README.md).

---

## Table of contents

**Part 1: MCP concepts**
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

**Part 2: Python SDK and tooling**
13. [SDK versions: v1 vs v2](#13-sdk-versions-v1-vs-v2)
14. [FastMCP vs low-level Server](#14-fastmcp-vs-low-level-server)
15. [Where the server runs (runtime)](#15-where-the-server-runs-runtime)
16. [`mcp.run()` is synchronous](#16-mcprun-is-synchronous)
17. [MCP Inspector](#17-mcp-inspector)
18. [What `uv run mcp install` does](#18-what-uv-run-mcp-install-does)

**Part 3: Python concepts used in `main.py`**
19. [Pydantic: BaseModel and Field](#19-pydantic-basemodel-and-field)
20. [`Annotated`](#20-annotated)
21. [`ValueError` and raising errors in tools](#21-valueerror-and-raising-errors-in-tools)
22. [`if __name__ == "__main__"`](#22-if-__name__--__main__)

**Part 4: uv and packaging**
23. [uv: the Python package manager](#23-uv-the-python-package-manager)
24. [pyproject.toml, uv.lock, requirements.txt](#24-pyprojecttoml-uvlock-requirementstxt)
25. [`mcp[cli]` and extras](#25-mcpcli-and-extras)
26. [Transitive dependencies](#26-transitive-dependencies)
27. [App vs package layout (`uv init` vs `uv init --package`)](#27-app-vs-package-layout)

**Part 5**
28. [Interview quick revision (Q&A)](#28-interview-quick-revision-qa)
29. [Official docs](#29-official-docs)

---

# Part 1: MCP concepts

## 1. MCP in one line

> **MCP (Model Context Protocol) is an open standard (by Anthropic, Nov 2024) for how AI apps discover and call external tools and data.** It's often called "USB-C for AI": build a tool once and plug it into any AI app.

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
4. App runs it:         -> {"employee_id": "E001", "balance": 18}
5. LLM answers user:    "E001 has 18 days of leave left."
```

### Why the docstring matters so much

The LLM **never sees the Python code**. It only sees:

- the function **name**: `get_leave_balance`
- the **parameters and types**: `employee_id: str` (plus `Field` descriptions and rules)
- the **docstring**: "Check how many leave days are left for an employee."

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

I never hand-write this JSON. The SDK (`MCPServer`) generates it from my function signature, type hints and docstring.

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
                                           │   MCP SERVER     │  <- src/main.py
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
| In this project | `src/main.py` | Claude Desktop / MCP Inspector |

**Host** = the full app the user sees (Claude Desktop). It contains the LLM and one MCP client per connected server.

### Restaurant analogy: "the server doesn't know about the LLM"

- **Customer** = user. **LLM** = decides what to order.
- **MCP client** = the waiter. It shows the menu (tool list), takes the order, carries the slip to the kitchen and brings the food back.
- **MCP server** = the kitchen. It never meets the customer. It only sees the slip:
  `tools/call  name: "get_leave_balance"  arguments: { employee_id: "E001" }`
- It doesn't know the user's English question, or whether Claude, Gemini or GPT is on the other side.
- **That's why the same server works with any LLM.**

### Server name

`MCPServer("LeaveManager")`: "LeaveManager" is just a label. It's sent in the `initialize` handshake (`serverInfo.name`), becomes the key in `claude_desktop_config.json`, shows in the Claude Desktop UI, and names the log file. It doesn't need to match file or function names.

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
        "properties": {
          "employee_id": { "type": "string", "description": "Employee ID like \"E001\"", "pattern": "^E\\d{3}$" }
        },
        "required": ["employee_id"]
      },
      "outputSchema": {
        "type": "object",
        "properties": { "employee_id": { "type": "string" }, "balance": { "type": "integer" } },
        "required": ["employee_id", "balance"]
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
  "result": {
    "content": [{ "type": "text", "text": "{\"employee_id\": \"E001\", \"balance\": 18}" }],
    "structuredContent": { "employee_id": "E001", "balance": 18 },
    "isError": false
  }
}
```

**Lifecycle:** `initialize` (handshake, agree on the protocol version, e.g. `2025-11-25`) → `tools/list` → `tools/call` (as many times as needed).

---

## 7. Tools, resources, prompts

An MCP server can expose 3 kinds of things (the 3 tabs in the Inspector):

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
| Code | `mcp.run()` | `mcp.run(transport="streamable-http")` |

This project uses **stdio**. (Older remote transport: HTTP + SSE, now replaced by streamable HTTP.)

**Why no `print()` in a stdio server:** stdout *is* the protocol channel. Extra text corrupts the JSON messages. Log to stderr instead: `print("msg", file=sys.stderr)`.

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

### Benefits

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
3. **Input validation.** Pydantic `Field` rules (e.g. `pattern`) reject bad arguments before my code runs.
4. **stdio is local.** No open port, so nothing is reachable from the internet.
5. **Remote auth.** Streamable HTTP servers use **OAuth 2.1** per the spec.

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
| MCP Inspector | Yes (a testing client) |
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

# Part 2: Python SDK and tooling

## 13. SDK versions: v1 vs v2

"v1" and "v2" are **versions of the `mcp` Python package** (the official SDK), using semantic versioning `MAJOR.MINOR.PATCH`. A **major** jump (1 → 2) allows breaking changes.

| | v1 (`mcp 1.x`) | v2 (`mcp 2.x`, used here: `2.3.0`) |
|---|---|---|
| Import | `from mcp.server.fastmcp import FastMCP` | `from mcp.server.mcpserver import MCPServer` |
| Create server | `FastMCP("LeaveManager")` | `MCPServer("LeaveManager")` |
| `@mcp.tool()`, docstrings, `mcp.run()` | Same | Same |

- v1 code on v2 gives `ModuleNotFoundError: No module named 'mcp.server.fastmcp'`.
- Check the version with `uv run mcp version`.
- To follow old tutorials exactly: `uv add "mcp[cli]<2"`.

**Don't confuse these three version numbers:**

| Thing | Example | What it is |
|---|---|---|
| `mcp` package (SDK) | `2.3.0` | The Python library I import |
| `fastmcp` package | `2.x`, `3.x` | A separate library with its own numbering |
| MCP protocol spec | `2025-11-25` | The rules of the JSON messages (agreed in `initialize`) |

---

## 14. FastMCP vs low-level Server

**FastMCP / MCPServer** = the high-level, decorator-based way. **Low-level `Server`** = the manual ("traditional") way.

Analogy: **Express vs Node's raw `http` module.**

**High-level (what I use):**
```python
mcp = MCPServer("LeaveManager")

@mcp.tool()
def get_leave_balance(employee_id: str) -> str:
    """Check leave balance."""
    return f"{employee_id} has 18 days"

mcp.run()
```
It automatically builds the JSON schema from type hints, uses the docstring as the description, answers `tools/list`, routes `tools/call`, formats results and sets up stdio.

**Low-level (v1 API shown):** I write it all by hand.
```python
server = Server("LeaveManager")

@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [types.Tool(name="get_leave_balance", description="...",
                       inputSchema={"type": "object", "properties": {"employee_id": {"type": "string"}},
                                    "required": ["employee_id"]})]

@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    if name == "get_leave_balance":
        return [types.TextContent(type="text", text=f"{arguments['employee_id']} has 18 days")]
    raise ValueError(f"Unknown tool: {name}")

async def main():
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())
```

**Use the high-level API unless you need full control.**

### "FastMCP" means three different things

1. **FastMCP 1.0**: originally a separate project, merged into the official SDK as `mcp.server.fastmcp` (v1).
2. **The `fastmcp` package** (gofastmcp.com, "The Framework for MCP"): continued separately with extra features (proxies, composition, auth helpers). `from fastmcp import FastMCP`.
3. **Official SDK v2**: renamed the built-in FastMCP to **`MCPServer`**.

---

## 15. Where the server runs (runtime)

| | Express (TS) | My MCP server |
|---|---|---|
| Runtime | **Node.js** (V8) | **CPython 3.12** (`python.exe`) |
| Packages live in | `node_modules/` | `.venv/` |
| Who starts it | **Me** (`npm start`) | **Claude Desktop** (as a child process) |
| Talks over | HTTP on a port | **stdin/stdout** (no port) |
| Clients | Many | One per process (each host starts its own) |
| Lifetime | Until I stop it | Starts and stops with Claude Desktop |

```
Claude Desktop ──stdin──►  python.exe (src/main.py)
  (parent)     ◄─stdout──  (child process)
```

You can see it in Task Manager as `python.exe` / `uv.exe` while Claude Desktop is open.

---

## 16. `mcp.run()` is synchronous

`mcp.run()` is a normal `def` (not `async`), so it's called **without `await`**. Inside, it **starts an event loop** and runs the async server (`run_stdio_async`).

- **It blocks.** Code after `mcp.run()` won't run until the server stops (like `app.listen()` keeping Node alive).
- **Don't call it inside async code** (an event loop is already running there). Use `await mcp.run_stdio_async()` instead.

**Python vs Node:** Node's event loop is always running. Python's must be **started explicitly** (`asyncio.run(...)`). `mcp.run()` does that for me.

Tools can be `def` or `async def`. Use `async def` when the tool waits on I/O (an HTTP call or DB query).

---

## 17. MCP Inspector

**The MCP Inspector is Postman for MCP servers.** It's an official testing tool with a web UI, and it **acts as an MCP client with no LLM**: *I* pick the tool and type the arguments.

```
uv run mcp dev src/main.py
   ├─ starts Inspector (Node, via npx)  → web page at 127.0.0.1:6274 (local only)
   └─ on Connect: starts my server via  uv run --with mcp==2.3.0 mcp run src/main.py  (stdio)
```

- The first run asks to install `@modelcontextprotocol/inspector` via npx (into npx's cache, not my project).
- `MCP_INSPECTOR_API_TOKEN` is a one-time session password that stops other programs controlling it. Don't share it.
- **Messages panel** shows the live JSON-RPC traffic: `tools/list`, `prompts/list`, `tools/call`…
- **Sandbox (MCP Apps)**: a separate port where servers returning interactive UI are shown safely. Not used here.

| Step | Tool | Tests |
|---|---|---|
| 1 | Inspector | "Does my server work?" (my code only) |
| 2 | Claude Desktop | "Does the AI use it correctly?" (code + LLM) |

---

## 18. What `uv run mcp install` does

Claude Desktop doesn't know my server exists. `uv run mcp install src/main.py` **writes an entry** into `%APPDATA%\Claude\claude_desktop_config.json`:

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

On every launch, Claude Desktop reads the config, runs that command (starting my server over stdio), sends `initialize` and `tools/list`, and shows the tools.

- **Why `uv` in the command?** It guarantees the right Python and packages every time.
- I could **paste the JSON by hand** instead. The result is the same.
- `mcp install` is **Claude Desktop only**. Cursor and VS Code use their own `mcp.json`.
- **Rerun it** after renaming the file or the server.

---

# Part 3: Python concepts used in `main.py`

## 19. Pydantic: BaseModel and Field

**Pydantic** is a data validation library, Python's **Zod**. It comes installed with `mcp`.

### BaseModel

A class inheriting `BaseModel` is a "smart data container". It's like a TS `interface` plus a Zod schema, but it **exists at runtime**.

```python
class LeaveBalance(BaseModel):
    employee_id: str = Field(description="Employee ID")
    balance: int = Field(description="Remaining leave days")
```

It gives:
1. **Validation + conversion:** `balance="18"` becomes `18`; `balance="abc"` raises `ValidationError`; a missing field raises an error.
2. **To JSON:** `obj.model_dump()` / `obj.model_dump_json()`.
3. **A JSON schema:** `LeaveBalance.model_json_schema()`.

In MCP, returning `-> LeaveBalance` gives the tool an **`outputSchema`** and a **structured JSON result** instead of plain text.

### Field

`Field` adds **meaning + rules + defaults** to a value:

| Option | Meaning | Zod equivalent |
|---|---|---|
| `description="..."` | Explains the field (the LLM reads it) | `.describe()` |
| `pattern=r"^E\d{3}$"` | Regex the string must match | `.regex()` |
| `ge=0` / `le=30` | Number ≥ / ≤ | `.min()` / `.max()` |
| `min_length` / `max_length` | Length limits | `.min()` / `.max()` |
| `default=0` | Fallback value | `.default()` |

### Regex `^E\d{3}$`

`^` start · `E` the letter E · `\d{3}` exactly 3 digits · `$` end. Matches `E001`; rejects `e001`, `E1`, `abc`.
`r"..."` = raw string, so backslashes reach the regex engine unchanged.

---

## 20. `Annotated`

`Annotated[type, extra_info]` attaches metadata to a type hint. It comes from the built-in `typing` module.

```python
employee_id: Annotated[str, Field(description='Employee ID like "E001"', pattern=r"^E\d{3}$")]
#                      type  extra info that Pydantic / the MCP SDK read (Python ignores it)
```

- Inside a `BaseModel` class: `name: str = Field(...)` is normal.
- For **function parameters**, `= something` means a default value, so `Annotated` is the clean, recommended way.
- Without it, the schema is just `{"type": "string"}`, with no description or validation.

---

## 21. `ValueError` and raising errors in tools

`ValueError` is a **built-in exception**: "right type, wrong value". It's like `throw new Error()` in JS.

| Exception | Meaning |
|---|---|
| `ValueError` | Right type, bad value |
| `TypeError` | Wrong type |
| `KeyError` | Dict key missing (`d["x"]`) |
| `IndexError` | List index out of range |

**In MCP: report failure by `raise`, not by `return`.** In SDK v2, **which** exception you raise matters too:

```python
from mcp.server.mcpserver.exceptions import ToolError

raise ToolError(f"Employee ID {employee_id} not found.")    # ✅ expected failure
raise ValueError(f"Employee ID {employee_id} not found.")   # ⚠️ treated as a CRASH
return ValueError(...)                                      # ❌ returns an object → output validation fails
```

| | `raise ToolError(...)` | `raise ValueError(...)` (any other exception) |
|---|---|---|
| Meaning to the SDK | "A failure I saw coming" | "The tool crashed" (`UnexpectedToolError`) |
| What the LLM sees | `isError: true` + **my message** | `isError: true` + only `Error executing tool get_leave_balance` (message hidden) |
| Server log | INFO, no traceback | ERROR + full traceback |

Why: v2 hides unexpected exception text from the client in case it contains internal details. Use `ToolError` for expected cases (not found, not allowed). Ordinary exceptions are for real bugs.

(Inside a Pydantic **validator**, `ValueError` is still the right thing to raise. Pydantic turns it into a validation error.)

`dict.get(key)` returns `None` for missing keys, while `dict[key]` raises `KeyError`. Read inner dict values with `data["balance"]`, not `data.balance`.

---

## 22. `if __name__ == "__main__"`

Python sets `__name__` automatically:

| How the file is used | `__name__` |
|---|---|
| Run directly (`python src/main.py`) | `"__main__"` (for **any** file name) |
| Imported (`import main`) | `"main"` (the file name) |

- `"__main__"` is a fixed special value, **not** related to the file being called `main.py`. Never change it.
- Node equivalent: `if (require.main === module)`.
- `mcp dev` / `mcp run` / `mcp install` import the file and start the `mcp` object themselves. The block lets the file also run on its own.
- File names can be anything (`server.py`, `leave_server.py`), as long as they're lowercase with underscores and no dashes. Don't name a file `mcp.py` or `pydantic.py`, because it would shadow the real packages.

---

# Part 4: uv and packaging

## 23. uv: the Python package manager

**uv** is a fast Python package and project manager written in Rust, by Astral. It replaces `pip`, `venv`, `pip-tools`, `poetry` and `pyenv`. **It's npm for Python.**

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
| `npm ls` | `uv tree` |

`uv init` also runs `git init` (a **local** repo, not GitHub). Skip it with `uv init <name> --vcs none`.

---

## 24. pyproject.toml, uv.lock, requirements.txt

| | `requirements.txt` | `pyproject.toml` |
|---|---|---|
| Lists dependencies | Yes | Yes (`dependencies = [...]`) |
| Project name, version, authors | No | Yes |
| Required Python version | No | Yes (`requires-python`) |
| Tool config (build system, scripts) | No | Yes |
| Auto-updated | No | Yes, by `uv add` |
| Status | Old convention | Official modern standard (PEP 621) |

**What to commit:**

| File | Commit? | Why |
|---|---|---|
| `pyproject.toml` | Yes | What I need (`mcp[cli]>=2.3.0`) |
| `uv.lock` | **Yes** | Exact versions of everything. `uv sync` reproduces them. |
| `.python-version` | Yes | Python version |
| `.venv/` | **No** | Installed packages (like `node_modules`) |
| `.env` | **No** | Secrets |

---

## 25. `mcp[cli]` and extras

`package[extra]` installs a package plus an **optional group of dependencies** (an "extra").

- `mcp` = the core library (`MCPServer`, `@mcp.tool()`). That's enough to run a server.
- `[cli]` = adds packages like `typer` for the **`mcp` command**: `mcp dev`, `mcp run`, `mcp install`, `mcp version`.
- Quote it in the shell (`uv add "mcp[cli]"`), because `[ ]` are special characters in Bash.

---

## 26. Transitive dependencies

I never ran `uv add pydantic`, but it's installed because **`mcp` depends on it** (a dependency of a dependency). That's why `uv add "mcp[cli]"` installed 38 packages. View them with `uv tree`.

**Best practice:** if my code **imports** a package directly, list it explicitly (`uv add pydantic`), so a future `mcp` release can't silently remove it.

---

## 27. App vs package layout

| | `uv init` (app) | `uv init --package` (package) |
|---|---|---|
| Layout | `main.py` in the root | `src/<name>/__init__.py` |
| `pyproject.toml` | Just `[project]` | Adds `[project.scripts]` + `[build-system]` |
| For | Scripts, servers | Libraries to publish/install |

- The folder is named twice (`leave-mcp-server/src/leave_mcp_server`) because Python import names **can't have dashes**, so uv converts them to underscores.
- `__init__.py` marks a folder as a Python package (like `index.js`).
- Error `Expected a Python module at: src\leave_mcp_server\__init__.py` = the package folder was deleted, but `[build-system]` still asks uv to build it. Remove `[project.scripts]` and `[build-system]`.

---

# Part 5

## 28. Interview quick revision (Q&A)

**Q: What is MCP?**
An open protocol by Anthropic (Nov 2024) that standardizes how AI applications connect to external tools, data and prompts. It's "USB-C for AI".

**Q: What problem does it solve?**
The M × N integration problem. Without it, every AI app needs custom glue for every data source and every LLM provider's tool format. With MCP it's M + N: build a server once and use it from any MCP client.

**Q: Host vs client vs server?**
Host = the user-facing AI app (Claude Desktop). Client = the connector inside the host (1:1 with a server). Server = the program exposing tools, resources and prompts.

**Q: Does the MCP server talk to the LLM?**
No. It only receives JSON-RPC requests like `tools/call` with a name and arguments. It's LLM-agnostic.

**Q: What protocol format does MCP use?**
JSON-RPC 2.0. Key methods: `initialize`, `tools/list`, `tools/call`, `resources/list`, `resources/read`, `prompts/list`, `prompts/get`.

**Q: Three primitives?**
Tools (model-controlled), resources (app-controlled read-only data), prompts (user-controlled templates).

**Q: Transports?**
stdio (local child process) and streamable HTTP (remote, OAuth). SSE is the older remote transport.

**Q: How does the LLM know which tool to call and with what arguments?**
The client gives the LLM each tool's name, description (the docstring) and input JSON schema (type hints + `Field`). The LLM maps the question to a tool and fills in the arguments.

**Q: Why is the docstring important?**
It's the only documentation the LLM sees. It drives tool selection and argument formatting.

**Q: MCP vs REST APIs / microservices?**
Different layers. REST is for developer-written programs; MCP is for LLMs that discover tools at runtime. MCP servers often wrap existing REST services.

**Q: MCP vs plain function calling?**
Function calling is the LLM capability. MCP is the provider-agnostic standard for packaging, discovering and connecting those functions across apps. MCP uses function calling underneath.

**Q: FastMCP vs low-level Server?**
FastMCP/MCPServer is high-level and decorator-based: it generates schemas from type hints and docstrings. The low-level Server needs manual `list_tools`/`call_tool` handlers and JSON schemas. It's like Express vs raw Node `http`.

**Q: What changed in the Python SDK v2?**
`FastMCP` was renamed to `MCPServer` (`from mcp.server.mcpserver import MCPServer`). Decorators and `run()` work the same.

**Q: Why use Pydantic in tools?**
Richer input schemas for the LLM (descriptions, patterns), automatic validation before the code runs, and structured output via `outputSchema`.

**Q: How should a tool report failure?**
Raise, don't return. In Python SDK v2, raise `ToolError` for expected failures: the LLM gets `isError: true` with my message. Any other exception counts as a crash: the message is hidden from the client and a traceback is logged at ERROR.

**Q: Security concerns?**
Untrusted servers run code locally; prompt injection through tool outputs; tool poisoning through descriptions; over-broad tools. Mitigations: least-privilege tools, input validation, human approval, trusted servers only, OAuth for remote servers, keeping secrets out of outputs.

**Q: What is the MCP Inspector?**
The official testing client (Postman for MCP). I act as the LLM, call tools manually and see the raw JSON-RPC.

**Q: What is uv?**
A fast Rust-based Python package and project manager, like npm for Python. `pyproject.toml` ≈ `package.json`, `uv.lock` ≈ `package-lock.json`, `.venv` ≈ `node_modules`.

**Q: What does `uv run mcp install src/main.py` do?**
It adds the server's start command to `claude_desktop_config.json`, so Claude Desktop launches it (stdio) and discovers its tools.

**Q: Can multiple clients use one MCP server?**
Yes. With stdio, each host starts its own process. With streamable HTTP, one deployed server serves many clients.

**Q: Why can't you `print()` in a stdio MCP server?**
stdout carries the JSON-RPC messages. Extra output corrupts the protocol. Log to stderr.

---

## 29. Official docs

| What | Link |
|---|---|
| MCP concepts and spec | https://modelcontextprotocol.io |
| Python SDK docs | https://py.sdk.modelcontextprotocol.io |
| v1 → v2 migration | https://py.sdk.modelcontextprotocol.io/v2/migration/ |
| Python SDK source | https://github.com/modelcontextprotocol/python-sdk |
| PyPI (`mcp`) | https://pypi.org/project/mcp/ |
| uv | https://docs.astral.sh/uv/ |
