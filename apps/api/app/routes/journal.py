from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app import models, schemas
from app.database import get_db

router = APIRouter()


@router.post("", response_model=schemas.JournalResponse)
async def create_journal_entry(
    entry_data: schemas.JournalCreate,
    current_user: dict = Depends(__import__('app.auth', fromlist=['get_current_user']).get_current_user),
    db: Session = Depends(get_db)
):
    """Create a trading journal entry."""
    entry = models.JournalEntry(
        user_id=current_user["user_id"],
        symbol=entry_data.symbol,
        trade_date=entry_data.trade_date,
        strategy=entry_data.strategy,
        entry_price=entry_data.entry_price,
        exit_price=entry_data.exit_price,
        result=entry_data.result,
        profit_loss=entry_data.profit_loss,
        emotion_before=entry_data.emotion_before,
        emotion_after=entry_data.emotion_after,
        mistake_category=entry_data.mistake_category,
        notes=entry_data.notes,
        lesson_learned=entry_data.lesson_learned
    )

    db.add(entry)
    db.commit()
    db.refresh(entry)

    return entry


@router.get("", response_model=list[schemas.JournalResponse])
async def list_journal_entries(
    current_user: dict = Depends(__import__('app.auth', fromlist=['get_current_user']).get_current_user),
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 50
):
    """List user's journal entries."""
    entries = db.query(models.JournalEntry).filter(
        models.JournalEntry.user_id == current_user["user_id"]
    ).offset(skip).limit(limit).all()

    return entries


@router.get("/{entry_id}", response_model=schemas.JournalResponse)
async def get_journal_entry(
    entry_id: int,
    current_user: dict = Depends(__import__('app.auth', fromlist=['get_current_user']).get_current_user),
    db: Session = Depends(get_db)
):
    """Get specific journal entry."""
    entry = db.query(models.JournalEntry).filter(
        models.JournalEntry.id == entry_id,
        models.JournalEntry.user_id == current_user["user_id"]
    ).first()

    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Journal entry not found"
        )

    return entry


@router.get("/analytics/summary")
async def get_journal_analytics(
    current_user: dict = Depends(__import__('app.auth', fromlist=['get_current_user']).get_current_user),
    db: Session = Depends(get_db)
):
    """Get trading journal analytics."""
    entries = db.query(models.JournalEntry).filter(
        models.JournalEntry.user_id == current_user["user_id"]
    ).all()

    total_trades = len(entries)
    wins = len([e for e in entries if e.result == "win"])
    losses = len([e for e in entries if e.result == "loss"])

    return {
        "total_trades": total_trades,
        "winning_trades": wins,
        "losing_trades": losses,
        "win_rate": (wins / total_trades * 100) if total_trades > 0 else 0,
        "best_performing_symbol": None,  # TODO: Calculate
        "worst_performing_symbol": None,  # TODO: Calculate
        "common_mistakes": None,  # TODO: Analyze
    }
