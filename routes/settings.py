from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db
from dependencies import get_current_user
from models import User
from schemas import UserSettings

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("", response_model=UserSettings)
def get_settings(current_user: User = Depends(get_current_user)):
    return current_user


@router.patch("", response_model=UserSettings)
def update_settings(
    data: UserSettings,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    changes = data.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(current_user, field, value)
    db.commit()
    db.refresh(current_user)
    return current_user
