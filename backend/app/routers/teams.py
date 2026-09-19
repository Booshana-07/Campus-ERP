from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from .. import models, schemas
from ..database import get_db
from ..deps import require_permanent_account

router = APIRouter(prefix="/api/teams", tags=["teams"])


@router.get("", response_model=list[schemas.TeamOut])
def list_teams(
    db: Session = Depends(get_db),
    # Phase 3A: a valid session is required.
    # Phase 3B: the team roster is campus operational data, so temporary
    # emergency-access accounts are excluded from it too.
    user: models.User = Depends(require_permanent_account),
):
    return db.query(models.ResponseTeam).all()
