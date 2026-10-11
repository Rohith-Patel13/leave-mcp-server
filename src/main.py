# =============================================================================
# Leave Manager: a beginner MCP server with ONE tool (get_leave_balance)
# =============================================================================
#
# BIG PICTURE
# -----------
# This file is an MCP SERVER (the "kitchen").
# An MCP CLIENT (Claude Desktop, the "waiter") starts this file, asks
# "what tools do you have?" (tools/list), and later says
# "run get_leave_balance with employee_id=E001" (tools/call).
# This server never sees the user's question or the LLM. It only receives
# the tool name + arguments, runs the Python function, and sends the result back.
#
# HOW TO RUN
# ----------
#   uv run mcp dev src/main.py       -> test in the browser (MCP Inspector)
#   uv run mcp install src/main.py   -> register with Claude Desktop
#
# IMPORTANT: never use print() in this file.
# Claude Desktop talks to this server through stdout (stdio transport).
# A print() would mix random text into the JSON messages and break the
# connection. For debugging use: print("msg", file=sys.stderr)
# =============================================================================


# -----------------------------------------------------------------------------
# IMPORTS
# -----------------------------------------------------------------------------

# `typing` is a BUILT-IN Python module (no install needed) with helpers for
# type hints.
# `Annotated[type, extra_info]` attaches extra info to a type hint.
#   Annotated[str, Field(...)]  means  "this is a str, AND here are its rules".
# Python itself ignores the extra info; Pydantic and the MCP SDK read it.
# IF MISSING: you can't attach a description or pattern to a function
# parameter cleanly. You'd fall back to a plain `employee_id: str`, and the
# LLM would only know "it's a string", with no description or format rule.
from typing import Annotated

# `pydantic` is a data validation library (Python's version of Zod in
# TypeScript). It's already installed because the `mcp` package depends on it.
#
# `BaseModel` is a base class for "data shapes". You describe the fields
#   once, and Pydantic gives you validation, conversion to JSON, and a JSON
#   schema for free. (Explained in detail at the LeaveBalance class below.)
#
# `Field(...)` adds details to a single field:
#   - description=... -> meaning (goes into the JSON schema, the LLM reads it)
#   - pattern=...     -> regex rule the string must match
#   - ge=0, le=30     -> number limits (>=, <=)
#   - default=...     -> fallback value
from pydantic import BaseModel, Field

# The official MCP Python SDK (package `mcp`, version 2.x).
# `MCPServer` is the high-level, easy server class. It does the protocol work:
# builds the tool list, validates inputs, routes calls, and formats results.
#   v1 name (old tutorials/video): from mcp.server.fastmcp import FastMCP
#   v2 name (what we have):        from mcp.server.mcpserver import MCPServer
# IF MISSING: you'd need the low-level `Server` API, which means writing the
# JSON schemas, the tools/list and tools/call handlers, and the stdio loop
# yourself (about 3x more code).
from mcp.server.mcpserver import MCPServer


# -----------------------------------------------------------------------------
# MOCK DATABASE
# -----------------------------------------------------------------------------
# A plain Python dictionary pretending to be the company's employee database.
# In real life, this would be a DB query or a call to an existing REST
# microservice. The MCP part of the code would stay exactly the same.
#
# Type hint: dict[str, dict[str, int]]
#   outer dict: key = employee ID (str)  -> value = another dict
#   inner dict: key = field name (str)   -> value = number (int)
#   e.g. "E001" -> {"balance": 18}
# Type hints don't change how the code runs. They help your editor
# (autocomplete, warnings) and readers.
# IF MISSING (the hint): the code works exactly the same, but you get less
# help from the editor.
employee_leaves: dict[str, dict[str, int]] = {
    "E001": {"balance": 18},
    "E002": {"balance": 20},
}


# -----------------------------------------------------------------------------
# CREATE THE MCP SERVER
# -----------------------------------------------------------------------------
# "LeaveManager" is just the server's NAME (a label you choose). It:
#   - is sent to the client in the `initialize` handshake (serverInfo.name)
#   - becomes the key in claude_desktop_config.json after `mcp install`
#   - shows in Claude Desktop under Settings -> Developer
#   - names the log file: %APPDATA%\Claude\logs\mcp-server-LeaveManager.log
# It doesn't need to match the file, folder or function names.
#
# `mcp` is the server object. Its decorator `@mcp.tool()` (below) registers
# functions as tools.
# IF MISSING: there's no server, so nothing to register tools on and nothing
# to run.
mcp = MCPServer("LeaveManager")


# -----------------------------------------------------------------------------
# OUTPUT MODEL: the shape of what the tool returns
# -----------------------------------------------------------------------------
# WHAT IS BaseModel?
#   A class that inherits from BaseModel becomes a "smart data container".
#   You list the fields with their types, and Pydantic gives you:
#
#   1. VALIDATION + CONVERSION when you create an object:
#        LeaveBalance(employee_id="E001", balance=18)     -> OK
#        LeaveBalance(employee_id="E001", balance="18")   -> OK, "18" becomes 18
#        LeaveBalance(employee_id="E001", balance="abc")  -> ValidationError
#        LeaveBalance(employee_id="E001")                 -> ValidationError (balance missing)
#
#   2. CONVERSION TO JSON / dict:
#        obj.model_dump()       -> {"employee_id": "E001", "balance": 18}
#        obj.model_dump_json()  -> '{"employee_id":"E001","balance":18}'
#
#   3. A JSON SCHEMA describing the shape:
#        LeaveBalance.model_json_schema()
#        -> {"type": "object",
#            "properties": {"employee_id": {"type": "string", ...},
#                           "balance":     {"type": "integer", ...}},
#            "required": ["employee_id", "balance"]}
#
#   TypeScript comparison: it's like an `interface` + a Zod schema in one.
#   A TS interface disappears at runtime, but BaseModel actually checks the
#   data while the program runs.
#
# WHY USE IT HERE?
#   Because the tool's return type is `-> LeaveBalance`, the MCP SDK:
#     - adds an `outputSchema` to the tool (clients know the result shape)
#     - returns STRUCTURED JSON:  {"employee_id": "E001", "balance": 18}
#       (and also a text copy of it, for clients that only read text)
#
# IF MISSING (if you returned a plain str instead):
#   the tool returns only a sentence like "E001 has 18 leave days remaining."
#   It works fine for chatting with Claude, but there's no outputSchema,
#   and any program reading the result has to parse text to get the number.
class LeaveBalance(BaseModel):
    # `employee_id: str` -> this field must be a string.
    # `= Field(description=...)` -> adds a description to the schema.
    # Inside a BaseModel class, `= Field(...)` is the normal way to add
    # details. (Because there's no `default=`, the field is still REQUIRED.)
    # IF Field IS MISSING: `employee_id: str` alone works; the schema just has
    # no description.
    employee_id: str = Field(description="Employee ID")

    # Must be an integer (whole number). Described as remaining leave days.
    balance: int = Field(description="Remaining leave days")


# -----------------------------------------------------------------------------
# THE TOOL
# -----------------------------------------------------------------------------
# `@mcp.tool()` is a DECORATOR: it wraps the function below and registers it
# as an MCP tool on the `mcp` server. From the function, the SDK builds:
#   - name         <- the function name: "get_leave_balance"
#   - description  <- the docstring ("""...""")
#   - inputSchema  <- the parameters + type hints + Field(...) info
#   - outputSchema <- the return type (LeaveBalance)
# Then it answers `tools/list` with that info, and routes every
# `tools/call` named "get_leave_balance" to this function.
#
# Node/Express comparison: like `app.get("/leave-balance", handler)`, which
# registers a handler for a route.
#
# IF MISSING (no decorator): it's just a normal Python function. Claude
# Desktop won't see it, and the tools list will be empty.
@mcp.tool()
def get_leave_balance(
    # PARAMETER: employee_id
    # Annotated[str, Field(...)] reads as: "a str, with these extra rules".
    #
    #   description -> shown to the LLM so it knows what to pass.
    #   pattern     -> a regex the value MUST match:  ^E\d{3}$
    #                    ^      start of the string
    #                    E      the letter E
    #                    \d{3}  exactly 3 digits (0-9)
    #                    $      end of the string
    #                  Matches: "E001", "E123"   Rejected: "e001", "E1", "abc"
    #
    #   The r"..." prefix means a RAW string: backslashes are kept as-is, so
    #   \d reaches the regex engine instead of being treated as a Python
    #   escape sequence.
    #
    # The SDK validates the input BEFORE this function runs. If the LLM sends
    # "abc", the SDK returns an error to the client and this code never runs.
    #
    # IF Field IS MISSING (plain `employee_id: str`): the LLM only knows "it's
    # a string", any text is accepted, and you'd have to validate it yourself.
    employee_id: Annotated[
        str,
        Field(description='Employee ID like "E001"', pattern=r"^E\d{3}$"),
    ],
# `-> LeaveBalance` is the RETURN TYPE hint: this function returns a
# LeaveBalance object. The SDK uses it to build the tool's outputSchema and
# to send the result as structured JSON.
# IF MISSING: the SDK can't build an outputSchema. Make it `-> str` and
# return a sentence if you want simple text output.
) -> LeaveBalance:
    # DOCSTRING: becomes the tool's `description`.
    # THIS IS WHAT THE LLM READS to decide WHEN to call this tool.
    # The LLM never sees the Python code, only the name, this docstring and
    # the schemas.
    # IF MISSING: the tool has no description. The LLM has to guess from the
    # name alone and may not call it, or call it at the wrong time.
    """Check how many leave days are left for an employee."""

    # dict.get(key) returns the value if the key exists, otherwise None.
    #   employee_leaves.get("E001") -> {"balance": 18}
    #   employee_leaves.get("E999") -> None
    # IF WE USED employee_leaves[employee_id] INSTEAD: an unknown ID would
    # crash with KeyError. With .get() we can handle it nicely ourselves.
    data = employee_leaves.get(employee_id)

    # `if not data` is True when data is None (employee not found).
    if not data:
        # Raising an exception inside a tool is the RIGHT way to report
        # failure. The SDK catches it and sends back a tool error
        # (is_error = true) with this message. Claude then knows the call
        # FAILED and can tell the user "employee not found".
        # IF WE RETURNED A NORMAL STRING INSTEAD: the result would look like a
        # success, and the error would be hidden inside normal-looking text.
        raise ValueError(f"Employee ID {employee_id} not found.")

    # Build the output object. Pydantic validates it (employee_id must be a
    # str, balance must be an int). The SDK then turns it into JSON:
    #   {"employee_id": "E001", "balance": 18}
    # data["balance"] reads the "balance" value from the inner dict.
    return LeaveBalance(employee_id=employee_id, balance=data["balance"])


# -----------------------------------------------------------------------------
# ENTRY POINT
# -----------------------------------------------------------------------------
# __name__ is a special variable Python sets automatically:
#   - "__main__" when this file is RUN directly   (python src/main.py)
#   - "main"     when this file is IMPORTED by other code (import main)
# So this block runs ONLY when the file is executed directly, not on import.
# Node comparison: like `if (require.main === module) { ... }`.
#
# mcp.run() starts the server and waits for messages. The default transport
# is "stdio": read requests from stdin, write responses to stdout.
# Other options: mcp.run(transport="streamable-http") for a remote/web server.
#
# IF MISSING:
#   - `python src/main.py` would define everything and exit immediately
#     (the server never starts listening).
#   - `uv run mcp dev` / `mcp run` / `mcp install` would still work, because
#     those commands import this file, find the `mcp` object and start it
#     themselves. Keeping this block lets the file run on its own too.
if __name__ == "__main__":
    mcp.run()
