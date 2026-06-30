from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from debatemind.database import get_db
from debatemind.models.user import User
from debatemind.schemas.auth import LoginIn, RegisterIn, TokenOut
from debatemind.services.auth import create_access_token, hash_password, verify_password
from debatemind.types import BadRequestError, EnityConflictError, SuccessResponse, UnauthorizedError

router = APIRouter()


@router.post(
    "/register",
    response_model=SuccessResponse[TokenOut],
    summary="Register new user",
    description=(
        "Create a new user account with email and password. Returns a JWT access token on success."
    ),
    responses={
        400: {"model": BadRequestError, "description": "Email already registered"},
        409: {"model": EnityConflictError, "description": "User already exists"},
    },
)
async def register(body: RegisterIn, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")
    user = User(email=body.email, hashed_password=hash_password(body.password))
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return SuccessResponse(
        data=TokenOut(
            access_token=create_access_token(user.id),
            user_id=user.id,
            calibration_done=user.calibration_done,
        )
    )


@router.post(
    "/login",
    response_model=SuccessResponse[TokenOut],
    summary="Login user",
    description="Authenticate with email and password. Returns a JWT access token on success.",
    responses={
        401: {"model": UnauthorizedError, "description": "Invalid email or password"},
    },
)
async def login(body: LoginIn, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()
    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return SuccessResponse(
        data=TokenOut(
            access_token=create_access_token(user.id),
            user_id=user.id,
            calibration_done=user.calibration_done,
        )
    )
