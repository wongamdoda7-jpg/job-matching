from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from typing import List
import uuid
from models import Payment, User, LoyaltyPoints, PaymentStatus
from schemas import PaymentRequest, PaymentResponse, LoyaltyPointsResponse
from main import get_db

router = APIRouter()

# Constants
PAYBACK_WINDOW_HOURS = 4
LOYALTY_POINTS_PER_RAND = 0.1  # 1 point per 10 ZAR

@router.post("/request-withdrawal", response_model=PaymentResponse, status_code=201)
def request_payment_withdrawal(
    payment_request: PaymentRequest,
    db: Session = Depends(get_db)
):
    """
    Request a payment withdrawal in South African Rand (ZAR)
    Payment will be processed within 4 hours to linked debit card
    """
    # Get user
    user = db.query(User).filter(User.id == payment_request.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Check if user has debit card linked
    if not user.debit_card_linked:
        raise HTTPException(
            status_code=400,
            detail="Debit card not linked. Please link a debit card first."
        )
    
    # Check sufficient balance
    if user.account_balance_zar < payment_request.amount_zar:
        raise HTTPException(
            status_code=400,
            detail=f"Insufficient balance. Available: R{user.account_balance_zar}"
        )
    
    # Create payment record
    transaction_id = str(uuid.uuid4())
    scheduled_for = datetime.utcnow() + timedelta(hours=PAYBACK_WINDOW_HOURS)
    
    payment = Payment(
        user_id=payment_request.user_id,
        amount_zar=payment_request.amount_zar,
        payment_type="earnings_withdrawal",
        status=PaymentStatus.PENDING,
        payment_method=payment_request.payment_method or "debit_card",
        transaction_id=transaction_id,
        scheduled_for=scheduled_for
    )
    
    # Deduct from user balance
    user.account_balance_zar -= payment_request.amount_zar
    
    db.add(payment)
    db.commit()
    db.refresh(payment)
    
    return PaymentResponse(
        id=payment.id,
        user_id=payment.user_id,
        amount_zar=payment.amount_zar,
        status=payment.status,
        payment_method=payment.payment_method,
        transaction_id=payment.transaction_id,
        scheduled_for=payment.scheduled_for,
        message=f"Payment scheduled within {PAYBACK_WINDOW_HOURS} hours to your debit card"
    )


@router.post("/redeem-loyalty-points", response_model=PaymentResponse, status_code=201)
def redeem_loyalty_points(
    user_id: int,
    points_to_redeem: int,
    db: Session = Depends(get_db)
):
    """
    Redeem loyalty points for South African Rand (ZAR)
    Points are converted to ZAR and added to account balance
    10 points = 1 ZAR
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Check sufficient points
    if user.loyalty_points < points_to_redeem:
        raise HTTPException(
            status_code=400,
            detail=f"Insufficient loyalty points. Available: {user.loyalty_points}"
        )
    
    # Convert points to ZAR (10 points = 1 ZAR)
    zar_amount = points_to_redeem / 10
    
    # Create redemption payment
    transaction_id = str(uuid.uuid4())
    
    payment = Payment(
        user_id=user_id,
        amount_zar=zar_amount,
        payment_type="bonus",
        status=PaymentStatus.COMPLETED,
        payment_method="loyalty_redemption",
        transaction_id=transaction_id,
        processed_at=datetime.utcnow()
    )
    
    # Add to user balance
    user.account_balance_zar += zar_amount
    user.loyalty_points -= points_to_redeem
    
    # Record loyalty history
    loyalty_record = LoyaltyPoints(
        user_id=user_id,
        points=-points_to_redeem,
        reason=f"Redeemed {points_to_redeem} points for R{zar_amount}",
        transaction_id=transaction_id
    )
    
    db.add(payment)
    db.add(loyalty_record)
    db.commit()
    db.refresh(payment)
    
    return PaymentResponse(
        id=payment.id,
        user_id=payment.user_id,
        amount_zar=payment.amount_zar,
        status=payment.status,
        payment_method=payment.payment_method,
        transaction_id=payment.transaction_id,
        message=f"Successfully redeemed {points_to_redeem} loyalty points for R{zar_amount}"
    )


@router.get("/status/{transaction_id}", response_model=PaymentResponse)
def get_payment_status(
    transaction_id: str,
    db: Session = Depends(get_db)
):
    """
    Check the status of a payment by transaction ID
    """
    payment = db.query(Payment).filter(
        Payment.transaction_id == transaction_id
    ).first()
    
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    
    # Check if payment should be marked as completed (within 4-hour window)
    if payment.status == PaymentStatus.PENDING:
        if datetime.utcnow() >= payment.scheduled_for:
            payment.status = PaymentStatus.COMPLETED
            payment.processed_at = datetime.utcnow()
            db.commit()
            db.refresh(payment)
    
    return PaymentResponse(
        id=payment.id,
        user_id=payment.user_id,
        amount_zar=payment.amount_zar,
        status=payment.status,
        payment_method=payment.payment_method,
        transaction_id=payment.transaction_id,
        scheduled_for=payment.scheduled_for,
        processed_at=payment.processed_at,
        message=f"Payment status: {payment.status}"
    )


@router.get("/user/{user_id}/balance")
def get_user_balance(
    user_id: int,
    db: Session = Depends(get_db)
):
    """
    Get user's current balance and loyalty points
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    return {
        "user_id": user_id,
        "account_balance_zar": user.account_balance_zar,
        "loyalty_points": user.loyalty_points,
        "debit_card_linked": user.debit_card_linked,
        "currency": "ZAR"
    }


@router.get("/user/{user_id}/history", response_model=List[PaymentResponse])
def get_payment_history(
    user_id: int,
    skip: int = 0,
    limit: int = 10,
    db: Session = Depends(get_db)
):
    """
    Get user's payment history
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    payments = db.query(Payment).filter(
        Payment.user_id == user_id
    ).order_by(Payment.created_at.desc()).offset(skip).limit(limit).all()
    
    return [
        PaymentResponse(
            id=p.id,
            user_id=p.user_id,
            amount_zar=p.amount_zar,
            status=p.status,
            payment_method=p.payment_method,
            transaction_id=p.transaction_id,
            scheduled_for=p.scheduled_for,
            processed_at=p.processed_at,
            message=f"Payment: {p.payment_type}"
        )
        for p in payments
    ]


@router.post("/add-loyalty-points")
def add_loyalty_points(
    user_id: int,
    points: int,
    reason: str,
    db: Session = Depends(get_db)
):
    """
    Add loyalty points to user account (admin/system use)
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    transaction_id = str(uuid.uuid4())
    
    # Add loyalty points
    user.loyalty_points += points
    
    # Record in loyalty history
    loyalty_record = LoyaltyPoints(
        user_id=user_id,
        points=points,
        reason=reason,
        transaction_id=transaction_id
    )
    
    db.add(loyalty_record)
    db.commit()
    
    return {
        "user_id": user_id,
        "points_added": points,
        "total_points": user.loyalty_points,
        "reason": reason,
        "transaction_id": transaction_id,
        "message": f"Added {points} loyalty points to user"
    }


@router.post("/link-debit-card")
def link_debit_card(
    user_id: int,
    card_token: str,  # Tokenized card from payment processor
    db: Session = Depends(get_db)
):
    """
    Link a debit card to user account for payouts
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # In production, integrate with payment processor (e.g., PayFast, Luno)
    user.debit_card_linked = True
    
    db.commit()
    
    return {
        "user_id": user_id,
        "debit_card_linked": True,
        "message": "Debit card successfully linked"
    }
