from fastapi import APIRouter, Depends
from .. import models, schemas
from ..ai_classifier import classify_incident
from ..deps import get_current_user

router = APIRouter(prefix="/api/ai", tags=["ai"])


@router.post("/analyze", response_model=schemas.AIAnalysisResult)
def analyze(
    payload: schemas.AIAnalyzeRequest,
    # Phase 3A: the AI endpoint costs real Groq quota, so it now requires a
    # signed-in, approved account rather than being open to the internet.
    user: models.User = Depends(get_current_user),
):
    """Standalone endpoint to preview AI/fallback classification without saving an incident."""
    return classify_incident(payload.description, payload.category or "", payload.location or "")
