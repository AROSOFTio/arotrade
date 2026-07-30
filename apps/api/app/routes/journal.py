from collections import Counter, defaultdict

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db

router = APIRouter()


@router.post("", response_model=schemas.JournalResponse)
async def create_journal_entry(
    entry_data: schemas.JournalCreate,
    current_user: dict = Depends(__import__('app.auth', fromlist=['get_current_user']).get_current_user),
    db: Session = Depends(get_db),
):
    entry = models.JournalEntry(
        user_id=current_user["user_id"],
        symbol=entry_data.symbol.upper(),
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
        lesson_learned=entry_data.lesson_learned,
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
    limit: int = 50,
):
    return db.query(models.JournalEntry).filter(
        models.JournalEntry.user_id == current_user["user_id"]
    ).order_by(models.JournalEntry.trade_date.desc()).offset(skip).limit(limit).all()


@router.get("/analytics/summary")
async def get_journal_analytics(
    current_user: dict = Depends(__import__('app.auth', fromlist=['get_current_user']).get_current_user),
    db: Session = Depends(get_db),
):
    entries = db.query(models.JournalEntry).filter(
        models.JournalEntry.user_id == current_user["user_id"]
    ).all()

    total_trades = len(entries)
    wins = sum(1 for entry in entries if entry.result == "win")
    losses = sum(1 for entry in entries if entry.result == "loss")
    pnl_by_symbol: dict[str, float] = defaultdict(float)
    mistakes: Counter[str] = Counter()
    for entry in entries:
        symbol = (entry.symbol or "UNKNOWN").upper()
        pnl_by_symbol[symbol] += float(entry.profit_loss or 0.0)
        if entry.mistake_category:
            mistakes[str(entry.mistake_category)] += 1

    ranked_symbols = sorted(pnl_by_symbol.items(), key=lambda item: item[1], reverse=True)
    return {
        "total_trades": total_trades,
        "winning_trades": wins,
        "losing_trades": losses,
        "win_rate": round((wins / total_trades * 100), 2) if total_trades > 0 else 0,
        "net_profit_loss": round(sum(pnl_by_symbol.values()), 2),
        "best_performing_symbol": ranked_symbols[0][0] if ranked_symbols else None,
        "worst_performing_symbol": ranked_symbols[-1][0] if ranked_symbols else None,
        "common_mistakes": [{"category": name, "count": count} for name, count in mistakes.most_common(5)],
    }


@router.get("/{entry_id}", response_model=schemas.JournalResponse)
async def get_journal_entry(
    entry_id: int,
    current_user: dict = Depends(__import__('app.auth', fromlist=['get_current_user']).get_current_user),
    db: Session = Depends(get_db),
):
    entry = db.query(models.JournalEntry).filter(
        models.JournalEntry.id == entry_id,
        models.JournalEntry.user_id == current_user["user_id"],
    ).first()
    if not entry:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Journal entry not found")
    return entry