# Leave Manager MCP server: one tool that returns an employee's leave balance.
#
# WORKFLOW
#   1. A client (Claude Desktop / MCP Inspector) starts this file as a child process.
#   2. They talk over stdin/stdout (stdio) using JSON-RPC messages.
#   3. Client asks "tools/list"   -> SDK replies with get_leave_balance + its schemas.
#   4. Client sends "tools/call"  -> SDK validates input -> runs our function
#                                 -> validates output -> sends the result back.
#
# Run:  uv run mcp dev src/main.py      (test in the Inspector)
#       uv run mcp install src/main.py  (register with Claude Desktop)
#
# Never print() here: stdout carries the protocol messages.
# Debug with print(..., file=sys.stderr).


# Pydantic = data validation library (like Zod). Installed along with `mcp`.
from pydantic import BaseModel

# Official MCP Python SDK v2. (v1 tutorials: `from mcp.server.fastmcp import FastMCP`.)
from mcp.server.mcpserver import MCPServer

# Create the server. "LeaveManager" is just its display name, sent to the
# client during the initialize handshake and shown in Claude Desktop.
mcp = MCPServer("LeaveManager")

# Mock database: a dict of dicts  { employee_id: { "balance": days } }.
# In real life this would be a DB query or a REST API call.
employee_data = {
   "EMP_001": {"balance": 18},
   "EMP_002": {"balance": 20}
}

# Output shape of the tool. Inheriting BaseModel gives:
#   - validation at runtime (balance must be an int, both fields required)
#   - an outputSchema for the tool, so clients know the result shape
#   - structured JSON output: {"employee_id": "EMP_001", "balance": 18}
class LeaveBalance(BaseModel):
   employee_id: str
   balance: int


# @mcp.tool() registers the function as an MCP tool. The SDK builds:
#   name         <- function name
#   description  <- docstring (what the LLM reads to decide when to call it)
#   inputSchema  <- parameters + type hints (employee_id: str)
#   outputSchema <- return type (-> LeaveBalance)
@mcp.tool()
def get_leave_balance(employee_id: str) -> LeaveBalance:
   """Retrieve the leave balance of a particular employee"""

   # dict.get() returns None for a missing key (dict["x"] would raise KeyError).
   data = employee_data.get(employee_id)

   # Not found: RAISE (don't return) so the call is marked as failed (isError: true).
   # Note: in SDK v2 a plain ValueError counts as a "crash", so the LLM sees only a
   # generic message. For expected failures, v2's way is ToolError
   # (from mcp.server.mcpserver.exceptions import ToolError), which passes this
   # message through to the LLM.
   if not data:
      raise ValueError(f"Employee id not found: {employee_id}")

   # data is a dict, so read it with ["balance"] (data.balance -> AttributeError).
   # The SDK turns this model into JSON for the client.
   return LeaveBalance(employee_id=employee_id, balance=data["balance"])

# True only when this file is run directly (not when imported).
# mcp.run() is synchronous: it starts the event loop and blocks, serving over
# stdio until the client disconnects. (mcp dev / mcp install start the `mcp`
# object themselves, so they don't depend on this block.)
if __name__ == "__main__":
   mcp.run()
