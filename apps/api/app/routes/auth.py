from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import timedelta
from app import models, schemas
from app.database import get_db
from app.auth import (
    hash_password, verify_password, create_access_token,
    create_refresh_token, verify_token, validate_password
)

router = APIRouter()


@router.post("/register", response_model=schemas.TokenResponse)
async def register(user_data: schemas.UserRegister, db: Session = Depends(get_db)):
    """Register a new user."""
    # Check if user exists
    existing_user = db.query(models.User).filter(
        models.User.email == user_data.email
    ).first()

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )

    # Validate password strength
    if not validate_password(user_data.password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password does not meet complexity requirements"
        )

    # Create user
    user = models.User(
        email=user_data.email,
        password_hash=hash_password(user_data.password),
        full_name=user_data.full_name or "",
        role=models.UserRole.TRADER,
        is_active=True
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    # Create tokens
    access_token = create_access_token({"sub": str(user.id)})
    refresh_token = create_refresh_token({"sub": str(user.id)})

    # Store session
    from datetime import datetime
    session = models.UserSession(
        user_id=user.id,
        token=access_token,
        refresh_token=refresh_token,
        expires_at=datetime.utcfromtimestamp(verify_token(access_token)["exp"])
    )
    db.add(session)
    db.commit()

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": 3600
    }


@router.post("/login", response_model=schemas.TokenResponse)
async def login(credentials: schemas.UserLogin, db: Session = Depends(get_db)):
    """Login user."""
    # Find user
    user = db.query(models.User).filter(
        models.User.email == credentials.email
    ).first()

    if not user or not verify_password(credentials.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials"
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive"
        )

    # Create tokens
    access_token = create_access_token({"sub": str(user.id)})
    refresh_token = create_refresh_token({"sub": str(user.id)})

    # Update last login
    user.last_login = __import__('datetime').datetime.utcnow()
    db.commit()

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": 3600
    }


@router.post("/refresh", response_model=schemas.TokenResponse)
async def refresh(refresh_token: str):
    """Refresh access token."""
    payload = verify_token(refresh_token)

    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token"
        )

    user_id = payload.get("sub")
    access_token = create_access_token({"sub": user_id})

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": 3600
    }


@router.get("/me", response_model=schemas.UserResponse)
async def get_current_user_info(
    current_user: dict = Depends(__import__('app.auth', fromlist=['get_current_user']).get_current_user),
    db: Session = Depends(get_db)
):
    """Get current user info."""
    user = db.query(models.User).filter(
        models.User.id == current_user["user_id"]
    ).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    if user.enable_live_trading and user.accepted_live_disclaimer and user.trading_mode != models.TradingMode.LIVE:
        user.trading_mode = models.TradingMode.LIVE
        db.commit()
        db.refresh(user)
    elif not user.enable_live_trading and user.trading_mode != models.TradingMode.DEMO:
        user.trading_mode = models.TradingMode.DEMO
        db.commit()
        db.refresh(user)

    return user


@router.patch("/me/settings", response_model=schemas.UserResponse)
async def update_current_user_settings(
    settings_data: schemas.UserSettingsUpdate,
    current_user: dict = Depends(__import__('app.auth', fromlist=['get_current_user']).get_current_user),
    db: Session = Depends(get_db)
):
    """Update non-execution risk preferences for the signed-in user."""
    user = db.query(models.User).filter(
        models.User.id == current_user["user_id"]
    ).first()

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    for field_name, value in settings_data.model_dump(exclude_none=True).items():
        setattr(user, field_name, value)

    db.commit()
    db.refresh(user)
    return user


@router.patch("/me/live-trading", response_model=schemas.UserResponse)
async def update_live_trading_preference(
    payload: schemas.LiveTradingUpdate,
    current_user: dict = Depends(__import__('app.auth', fromlist=['get_current_user']).get_current_user),
    db: Session = Depends(get_db)
):
    """Let the signed-in user opt in or out of live trading themselves.

    Opting in requires explicitly accepting the risk disclaimer. Note that a
    broker adapter must also be connected before live orders can flow.
    """
    user = db.query(models.User).filter(
        models.User.id == current_user["user_id"]
    ).first()

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if payload.enable and not payload.accept_risk_disclaimer:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You must accept the live-trading risk disclaimer to enable live trading"
        )

    previous_mode = user.trading_mode.value if user.trading_mode else None
    user.enable_live_trading = payload.enable
    user.trading_mode = models.TradingMode.LIVE if payload.enable else models.TradingMode.DEMO
    if payload.enable:
        user.accepted_live_disclaimer = True

    audit = models.AuditLog(
        user_id=user.id,
        action="self_service_live_trading",
        resource="user",
        resource_id=user.id,
        changes={
            "enable_live_trading": payload.enable,
            "accepted_live_disclaimer": bool(payload.enable),
            "trading_mode": {
                "from": previous_mode,
                "to": user.trading_mode.value,
            },
        }
    )
    db.add(audit)
    db.commit()
    db.refresh(user)
    return user


@router.post("/logout")
async def logout(current_user: dict = Depends(__import__('app.auth', fromlist=['get_current_user']).get_current_user)):
    """Logout user."""
    # Token invalidation would happen via blacklist in production
    return {"message": "Logged out successfully"}
