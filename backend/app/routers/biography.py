"""Biography generation and export API endpoints."""

from fastapi import APIRouter
from fastapi.responses import Response
from app.services.biography_generator import generate_biography
from app.services.export_engine import export_biography
from app.config import settings

router = APIRouter(prefix="/api")


@router.get("/biography")
async def get_biography():
    """Generate and return a prose biography."""
    content = await generate_biography(settings.USER_NAME)
    return {"biography": content, "user_name": settings.USER_NAME}


@router.get("/export")
async def export(format: str = "markdown"):
    """Export biography in the specified format (markdown, txt, html, pdf, docx)."""
    content = await generate_biography(settings.USER_NAME)
    file_bytes, filename, content_type = await export_biography(
        content, format, settings.USER_NAME
    )
    return Response(
        content=file_bytes,
        media_type=content_type,
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
