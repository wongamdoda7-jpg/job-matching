from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
from datetime import datetime
import uuid

from models import Application, Job, User, LoyaltyPoints, Notification
from schemas import ApplicationCreate, ApplicationResponse
from routers.auth import get_current_user
from main import get_db

router = APIRouter()

# ============ Application Management ============

@router.post("/apply", response_model=ApplicationResponse, status_code=201)
def submit_application(
    app_data: ApplicationCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Submit an application for a job
    - Awards 10 loyalty points for submission
    - Awards 50 loyalty points if accepted
    """
    # Verify job exists
    job = db.query(Job).filter(Job.id == app_data.job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    # Check if job is active
    if job.status != "active":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This job is no longer accepting applications"
        )
    
    # Check if user already applied
    existing_app = db.query(Application).filter(
        Application.job_id == app_data.job_id,
        Application.user_id == current_user.id
    ).first()
    
    if existing_app:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You have already applied for this job"
        )
    
    # Create application
    db_application = Application(
        job_id=app_data.job_id,
        user_id=current_user.id,
        cover_letter=app_data.cover_letter,
        status="pending"
    )
    
    db.add(db_application)
    db.flush()
    
    # Award loyalty points for application (10 points)
    current_user.loyalty_points += 10
    
    loyalty_record = LoyaltyPoints(
        user_id=current_user.id,
        points=10,
        reason=f"Applied for job: {job.title}",
        transaction_id=str(uuid.uuid4())
    )
    db.add(loyalty_record)
    
    # Create notification
    notification = Notification(
        user_id=current_user.id,
        type="application_status",
        message=f"Application submitted for '{job.title}' - You earned 10 loyalty points!"
    )
    db.add(notification)
    
    db.commit()
    db.refresh(db_application)
    
    return ApplicationResponse.from_orm(db_application)

@router.get("/my-applications", response_model=List[ApplicationResponse])
def get_my_applications(
    status: Optional[str] = None,
    skip: int = 0,
    limit: int = 20,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get current user's job applications
    Optional filter by status: pending, accepted, rejected, withdrawn
    """
    query = db.query(Application).filter(
        Application.user_id == current_user.id
    )
    
    if status:
        query = query.filter(Application.status == status)
    
    applications = query.order_by(
        Application.created_at.desc()
    ).offset(skip).limit(limit).all()
    
    return [ApplicationResponse.from_orm(app) for app in applications]

@router.get("/{application_id}", response_model=ApplicationResponse)
def get_application(
    application_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get application details
    User can only view their own applications
    Employer can view applicants' applications
    """
    application = db.query(Application).filter(
        Application.id == application_id
    ).first()
    
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")
    
    # Verify access permissions
    from models import Employer
    job = db.query(Job).filter(Job.id == application.job_id).first()
    employer = db.query(Employer).filter(
        Employer.id == job.employer_id
    ).first()
    
    is_applicant = application.user_id == current_user.id
    is_employer = employer and employer.email == current_user.email
    
    if not is_applicant and not is_employer:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to view this application"
        )
    
    return ApplicationResponse.from_orm(application)

@router.put("/{application_id}/status", response_model=ApplicationResponse)
def update_application_status(
    application_id: int,
    new_status: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Update application status (employer only)
    Valid statuses: pending, accepted, rejected, withdrawn
    
    - Accepted: Awards 50 loyalty points to applicant
    - Rejected: No additional points
    """
    application = db.query(Application).filter(
        Application.id == application_id
    ).first()
    
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")
    
    # Validate status
    valid_statuses = ["pending", "accepted", "rejected", "withdrawn"]
    if new_status not in valid_statuses:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid status. Must be one of: {', '.join(valid_statuses)}"
        )
    
    # Verify employer ownership
    from models import Employer
    job = db.query(Job).filter(Job.id == application.job_id).first()
    employer = db.query(Employer).filter(
        Employer.id == job.employer_id
    ).first()
    
    if not employer or employer.email != current_user.email:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the employer can update application status"
        )
    
    old_status = application.status
    application.status = new_status
    application.updated_at = datetime.utcnow()
    
    # Get applicant
    applicant = db.query(User).filter(User.id == application.user_id).first()
    
    # Award loyalty points for acceptance
    if new_status == "accepted" and old_status != "accepted":
        applicant.loyalty_points += 50
        
        loyalty_record = LoyaltyPoints(
            user_id=application.user_id,
            points=50,
            reason=f"Job application accepted: {job.title}",
            transaction_id=str(uuid.uuid4())
        )
        db.add(loyalty_record)
        
        message = f"Congratulations! Your application for '{job.title}' was accepted! You earned 50 loyalty points!"
    elif new_status == "rejected":
        message = f"Your application for '{job.title}' was not selected. Don't give up, keep applying!"
    elif new_status == "withdrawn":
        message = f"Your application for '{job.title}' has been withdrawn."
    else:
        message = f"Your application status changed to {new_status}"
    
    # Create notification
    notification = Notification(
        user_id=application.user_id,
        type="application_status",
        message=message
    )
    db.add(notification)
    
    db.commit()
    db.refresh(application)
    
    return ApplicationResponse.from_orm(application)

@router.delete("/{application_id}", status_code=204)
def withdraw_application(
    application_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Withdraw an application (applicant only)
    """
    application = db.query(Application).filter(
        Application.id == application_id
    ).first()
    
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")
    
    if application.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only withdraw your own applications"
        )
    
    if application.status in ["withdrawn", "accepted"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot withdraw application with status '{application.status}'"
        )
    
    application.status = "withdrawn"
    application.updated_at = datetime.utcnow()
    
    db.commit()

@router.get("/stats/summary")
def get_application_stats(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get user's application statistics
    """
    total = db.query(func.count(Application.id)).filter(
        Application.user_id == current_user.id
    ).scalar() or 0
    
    accepted = db.query(func.count(Application.id)).filter(
        Application.user_id == current_user.id,
        Application.status == "accepted"
    ).scalar() or 0
    
    pending = db.query(func.count(Application.id)).filter(
        Application.user_id == current_user.id,
        Application.status == "pending"
    ).scalar() or 0
    
    rejected = db.query(func.count(Application.id)).filter(
        Application.user_id == current_user.id,
        Application.status == "rejected"
    ).scalar() or 0
    
    acceptance_rate = f"{(accepted / total * 100):.1f}%" if total > 0 else "0%"
    
    return {
        "total_applications": total,
        "accepted": accepted,
        "pending": pending,
        "rejected": rejected,
        "acceptance_rate": acceptance_rate
    }

@router.get("/user/{user_id}/summary")
def get_user_application_summary(
    user_id: int,
    db: Session = Depends(get_db)
):
    """
    Get any user's application summary (public view)
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    total = db.query(func.count(Application.id)).filter(
        Application.user_id == user_id
    ).scalar() or 0
    
    accepted = db.query(func.count(Application.id)).filter(
        Application.user_id == user_id,
        Application.status == "accepted"
    ).scalar() or 0
    
    return {
        "user_id": user_id,
        "user_name": user.full_name,
        "total_applications": total,
        "successful_applications": accepted,
        "loyalty_points": user.loyalty_points
    }
