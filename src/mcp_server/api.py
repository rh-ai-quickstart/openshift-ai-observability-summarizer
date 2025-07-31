"""FastAPI application setup for Observability MCP Server.

Simple MCP server without authentication for internal use.
"""

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from mcp_server.mcp import ObservabilityMCPServer

server = ObservabilityMCPServer()

# Standard HTTP transport for MCP
mcp_app = server.mcp.http_app(path="/mcp")

# Initialize FastAPI with MCP lifespan
app = FastAPI(lifespan=mcp_app.lifespan)


@app.get("/health")
async def health_check():
    """Health check endpoint for the MCP server."""
    return JSONResponse(
        status_code=200,
        content={
            "status": "healthy",
            "service": "observability-mcp-server",
            "version": "1.0.0",
            "mcp_endpoint": "/mcp",
        },
    )


# Mount the MCP app at root level
app.mount("/", mcp_app)


