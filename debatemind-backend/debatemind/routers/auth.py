import secrets

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from debatemind.config import settings
from debatemind.database import get_db
from debatemind.models.user import User
from debatemind.schemas.auth import ClerkExchangeIn, LoginIn, RegisterIn, TokenOut
from debatemind.services.auth import (
    create_access_token,
    hash_password,
    verify_clerk_jwt,
    verify_password,
)
from debatemind.types import BadRequestError, SuccessResponse, UnauthorizedError

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


@router.post(
    "/clerk-exchange",
    response_model=SuccessResponse[TokenOut],
    summary="Exchange Clerk session token for a backend token",
)
async def clerk_exchange(body: ClerkExchangeIn, db: AsyncSession = Depends(get_db)):
    try:
        payload = await verify_clerk_jwt(body.clerk_token)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid Clerk token")

    clerk_user_id: str = payload.get("sub", "")
    if not clerk_user_id:
        raise HTTPException(status_code=401, detail="Invalid Clerk token")

    # Fetch email from Clerk API (best-effort)
    email: str | None = None
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"https://api.clerk.com/v1/users/{clerk_user_id}",
                headers={"Authorization": f"Bearer {settings.clerk_secret_key}"},
                timeout=10,
            )
            if r.is_success:
                data = r.json()
                primary_id = data.get("primary_email_address_id")
                email = next(
                    (
                        e["email_address"]
                        for e in data.get("email_addresses", [])
                        if e.get("id") == primary_id
                    ),
                    None,
                )
    except Exception:
        pass

    # 1. Look up by clerk_id
    result = await db.execute(select(User).where(User.clerk_id == clerk_user_id))
    user = result.scalar_one_or_none()

    # 2. Link existing email/password account to Clerk
    if not user and email:
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()
        if user:
            user.clerk_id = clerk_user_id
            await db.commit()
            await db.refresh(user)

    # 3. Create new user
    if not user:
        user = User(
            email=email or f"{clerk_user_id}@clerk.user",
            hashed_password=hash_password(secrets.token_hex(32)),
            clerk_id=clerk_user_id,
        )
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
