---
language: python
tags: [ai, mcp, model-context-protocol, server, tools, resources]
title: MCP (Model Context Protocol) Server Basics
description: Building a minimal MCP server with Python — tools, resources, prompts, and stdio transport
source: pattern
---

```python
"""
Minimal MCP server using the official Python SDK.

Run with:
    python mcp_server_basics.py

Connect via stdio:
    mcp_client --transport stdio --command "python mcp_server_basics.py"

Or manually with any MCP client:
    echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}' | python mcp_server_basics.py
"""

from mcp.server import Server, NotificationOptions
from mcp.server.models import InitializationOptions
from mcp.types import (
    TextContent,
    Tool,
    Resource,
    ResourceTemplate,
    Prompt,
    PromptMessage,
    PromptArgument,
)
from pydantic import AnyUrl
import httpx
import json

# ——— Server instance ———
server = Server("example-server")

# ——— 1. Tools (callable by the LLM) ———


@server.list_tools()
async def handle_list_tools() -> list[Tool]:
    return [
        Tool(
            name="get_weather",
            description="Get current weather for a location",
            inputSchema={
                "type": "object",
                "properties": {
                    "location": {"type": "string"},
                    "unit": {
                        "type": "string",
                        "enum": ["celsius", "fahrenheit"],
                        "default": "celsius",
                    },
                },
                "required": ["location"],
            },
        ),
        Tool(
            name="calculator",
            description="Evaluate a mathematical expression",
            inputSchema={
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "e.g. '2 + 2' or 'sqrt(16)'",
                    }
                },
                "required": ["expression"],
            },
        ),
    ]


@server.call_tool()
async def handle_call_tool(name: str, arguments: dict) -> list[TextContent]:
    if name == "get_weather":
        location = arguments["location"]
        unit = arguments.get("unit", "celsius")
        # Replace with real API call as needed
        result = json.dumps({
            "location": location,
            "temperature": 22 if unit == "celsius" else 72,
            "unit": unit,
            "conditions": "partly cloudy",
        })
        return [TextContent(type="text", text=result)]

    elif name == "calculator":
        expression = arguments["expression"]
        try:
            result = str(eval(expression, {"__builtins__": {}}, {}))
        except Exception as e:
            result = f"Error: {e}"
        return [TextContent(type="text", text=result)]

    raise ValueError(f"Unknown tool: {name}")

# ——— 2. Resources (data exposed to the LLM) ———


@server.list_resources()
async def handle_list_resources() -> list[Resource]:
    return [
        Resource(
            uri=AnyUrl("docs://postgres/connection"),
            name="PostgreSQL Connection Guide",
            description="How to connect to a PostgreSQL database",
            mimeType="text/markdown",
        ),
        Resource(
            uri=AnyUrl("config://app/settings"),
            name="Application Settings",
            description="Current app configuration",
            mimeType="application/json",
        ),
    ]


@server.read_resource()
async def handle_read_resource(uri: AnyUrl) -> str:
    if str(uri) == "docs://postgres/connection":
        return "## PostgreSQL Connection\n\nConnect via: `psql -h localhost -U user db`"
    elif str(uri) == "config://app/settings":
        return json.dumps({"host": "localhost", "port": 5432, "debug": False})
    raise ValueError(f"Unknown resource: {uri}")


# Optional: resource templates (dynamic URIs)
@server.list_resource_templates()
async def handle_list_resource_templates() -> list[ResourceTemplate]:
    return [
        ResourceTemplate(
            uriTemplate="docs://{category}/{slug}",
            name="Documentation pages",
            description="Access any doc page by category and slug",
        )
    ]

# ——— 3. Prompts (reusable prompt templates) ———


@server.list_prompts()
async def handle_list_prompts() -> list[Prompt]:
    return [
        Prompt(
            name="translate",
            description="Translate text to a target language",
            arguments=[
                PromptArgument(
                    name="text",
                    description="Text to translate",
                    required=True,
                ),
                PromptArgument(
                    name="target_lang",
                    description="Target language (e.g. 'French')",
                    required=True,
                ),
            ],
        )
    ]


@server.get_prompt()
async def handle_get_prompt(name: str, arguments: dict | None) -> list[PromptMessage]:
    if name == "translate":
        text = arguments.get("text", "")
        lang = arguments.get("target_lang", "French")
        return [
            PromptMessage(
                role="user",
                content=TextContent(
                    type="text",
                    text=f"Translate the following text to {lang}. "
                         f"Only respond with the translation, no explanations.\n\n{text}",
                ),
            )
        ]
    raise ValueError(f"Unknown prompt: {name}")

# ——— Run with stdio transport ———

async def main():
    async with server.run_stdio() as server_stream:
        # The server handles JSON-RPC messages over stdin/stdout
        print("MCP server ready (stdio transport)", file=__import__("sys").stderr)
        await server_stream

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
```