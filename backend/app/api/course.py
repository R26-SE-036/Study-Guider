"""The Java foundations course. Read-only.

Signed-in students only, like every other route here. Nothing below writes:
reading a unit or answering its practice questions is not a knowledge-tracing
observation (see app/services/course_service.py). Units come from files, so
these answer even while the graph or the language model is unavailable.
"""

from fastapi import APIRouter, Depends, HTTPException

from app.core.auth import CurrentUser, get_current_user
from app.services import course_service

router = APIRouter()


@router.get("")
def get_catalogue(_user: CurrentUser = Depends(get_current_user)):
    return course_service.catalogue()


@router.get("/units/{unit_id}")
def get_unit(unit_id: str, _user: CurrentUser = Depends(get_current_user)):
    try:
        return course_service.unit_view(unit_id.upper())
    except course_service.UnitNotFound:
        raise HTTPException(status_code=404, detail="That unit is not in the course yet.")
