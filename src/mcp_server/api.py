"""FastAPI application setup for Observability MCP Server with report endpoints."""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse

from mcp_server.observability_mcp import ObservabilityMCPServer
from mcp_server.settings import settings

# Import report-related modules with error handling for clearer diagnostics
try:
    from core.reports import (
        save_report,
        get_report_path,
        build_report_schema,
    )
    from core.models import ReportRequest
    from core.report_assets.report_renderer import (
        generate_html_report,
        generate_markdown_report,
        generate_pdf_report,
    )
except ImportError as e:
    raise RuntimeError(
        f"Failed to import report-related modules from 'core'. "
        f"Ensure you are running from the correct environment (src/) and that all dependencies are installed. "
        f"Original error: {e}"
    ) from e

server = ObservabilityMCPServer()

# Select transport protocol
if settings.MCP_TRANSPORT_PROTOCOL == "sse":
    from fastmcp.server.http import create_sse_app  # type: ignore

    mcp_app = create_sse_app(server.mcp, message_path="/sse/message", sse_path="/sse")
else:
    mcp_app = server.mcp.http_app(path="/mcp")

# Initialize FastAPI with MCP lifespan
app = FastAPI(lifespan=mcp_app.lifespan)

# Optional CORS
if settings.CORS_ENABLED:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=settings.CORS_CREDENTIALS,
        allow_methods=settings.CORS_METHODS,
        allow_headers=settings.CORS_HEADERS,
    )


@app.get("/health")
async def health_check():
    return JSONResponse(
        status_code=200,
        content={
            "status": "healthy",
            "service": "observability-mcp-server",
            "transport_protocol": settings.MCP_TRANSPORT_PROTOCOL,
            "mcp_endpoint": "/mcp",
            "report_endpoints": ["POST /generate_report", "GET /download_report/{report_id}"]
        },
    )


# === REPORT ENDPOINTS (moved from metrics-api) ===

@app.get("/download_report/{report_id}")
def download_report(report_id: str):
    """Download generated report"""
    try:
        report_path = get_report_path(report_id)
        return FileResponse(report_path)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Report {report_id} not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving report: {str(e)}")


@app.post("/generate_report")
def generate_report(request: ReportRequest):
    """Generate report in requested format"""
    try:
        # Check if we have analysis data from UI session
        if (
            request.health_prompt is None
            or request.llm_summary is None
            or request.metrics_data is None
        ):
            raise HTTPException(
                status_code=400,
                detail="No analysis data provided. Please run analysis first.",
            )

        # Build the unified report schema once
        report_schema = build_report_schema(
            request.metrics_data,
            request.llm_summary,
            request.model_name,
            request.start_ts,
            request.end_ts,
            request.summarize_model_id,
            request.trend_chart_image,
        )

        # Generate report content based on format
        format_lower = request.format.lower()
        if format_lower == "html":
            report_content = generate_html_report(report_schema)
        elif format_lower == "pdf":
            report_content = generate_pdf_report(report_schema)
        elif format_lower == "markdown":
            report_content = generate_markdown_report(report_schema)
        else:
            raise HTTPException(
                status_code=400, detail=f"Unsupported format: {request.format}"
            )

        # Save and send
        report_id = save_report(report_content, request.format)
        return {"report_id": report_id, "download_url": f"/download_report/{report_id}"}

    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        # Handle any other exceptions
        raise HTTPException(status_code=500, detail=f"Error generating report: {str(e)}")


# === CRITICAL: MCP app must be mounted LAST ===
# This catches all unmatched routes and forwards them to MCP tools
# Adding any routes after this mount will break the application
def _enforce_no_routes_after_mount():
    """Prevent accidental route additions after MCP mount."""
    def _blocked_route(*args, **kwargs):
        raise RuntimeError(
            "Cannot add routes after mounting MCP app at root. "
            "Move all route definitions before app.mount('/', mcp_app)"
        )
    
    app.add_route = _blocked_route
    app.add_api_route = _blocked_route

# Mount MCP app and lock further route additions
app.mount("/", mcp_app)
_enforce_no_routes_after_mount()


