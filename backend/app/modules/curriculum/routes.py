"""HTTP endpoints for the curriculum module."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.models import User
from app.modules.curriculum.exceptions import AlreadyEnrolled, CourseNotFound
from app.modules.curriculum.schemas import EnrollmentCreate, EnrollmentRead
from app.modules.curriculum.service import EnrollmentService

router = APIRouter(prefix="/courses", tags=["courses"])


@router.post(
    "/enroll",
    response_model=EnrollmentRead,
    status_code=status.HTTP_201_CREATED,
)
def enroll_in_course(
    payload: EnrollmentCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> EnrollmentRead:
    """Enroll the authenticated user in a course by slug.

    Returns 409 if the user is already enrolled (MVP: one per user).
    Returns 404 if the slug doesn't match any course.
    """
    service = EnrollmentService(db)
    try:
        enrollment = service.enroll(
            user_id=current_user.id,
            course_slug=payload.course_slug,
        )
    except CourseNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))
    except AlreadyEnrolled as e:
        raise HTTPException(status_code=409, detail=str(e))

    return EnrollmentRead.model_validate(enrollment)