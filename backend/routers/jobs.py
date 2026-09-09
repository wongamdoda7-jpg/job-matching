from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime

from models import Job, Employer, JobSkill, Skill, User
from schemas import JobCreate, JobResponse, SkillCreate, SkillResponse
from routers.auth import get_current_user
from main import get_db

router = APIRouter()

# ============ Skill Management ============

@router.post("/skills", response_model=SkillResponse, status_code=201)
def create_skill(
    skill_data: SkillCreate,
    db: Session = Depends(get_db)
):
    """
    Create a new skill (admin/system use)
    """
    # Check if skill already exists
    existing_skill = db.query(Skill).filter(Skill.name == skill_data.name).first()
    if existing_skill:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Skill already exists"
        )
    
    db_skill = Skill(
        name=skill_data.name,
        category=skill_data.category
    )
    
    db.add(db_skill)
    db.commit()
    db.refresh(db_skill)
    
    return SkillResponse.from_orm(db_skill)

@router.get("/skills", response_model=List[SkillResponse])
def list_skills(
    category: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """
    List all available skills with optional category filter
    """
    query = db.query(Skill)
    
    if category:
        query = query.filter(Skill.category == category)
    
    skills = query.offset(skip).limit(limit).all()
    return [SkillResponse.from_orm(skill) for skill in skills]

@router.get("/skills/{skill_id}", response_model=SkillResponse)
def get_skill(skill_id: int, db: Session = Depends(get_db)):
    """
    Get a specific skill by ID
    """
    skill = db.query(Skill).filter(Skill.id == skill_id).first()
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    
    return SkillResponse.from_orm(skill)

# ============ Job Listings ============

@router.post("/create", response_model=JobResponse, status_code=201)
def create_job(
    job_data: JobCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Create a new job posting (employer only)
    """
    # Verify user is an employer
    employer = db.query(Employer).filter(Employer.email == current_user.email).first()
    if not employer:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only employers can create job postings"
        )
    
    # Create job
    db_job = Job(
        employer_id=employer.id,
        title=job_data.title,
        description=job_data.description,
        location=job_data.location,
        salary_min=job_data.salary_min,
        salary_max=job_data.salary_max,
        job_type=job_data.job_type,
        status="active"
    )
    
    db.add(db_job)
    db.flush()
    
    # Add skills required
    if job_data.skills_required:
        for skill_id in job_data.skills_required:
            skill = db.query(Skill).filter(Skill.id == skill_id).first()
            if not skill:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Skill with ID {skill_id} not found"
                )
            
            job_skill = JobSkill(
                job_id=db_job.id,
                skill_id=skill_id
            )
            db.add(job_skill)
    
    db.commit()
    db.refresh(db_job)
    
    return JobResponse.from_orm(db_job)

@router.get("", response_model=List[JobResponse])
def list_jobs(
    location: Optional[str] = None,
    job_type: Optional[str] = None,
    status: Optional[str] = "active",
    skip: int = 0,
    limit: int = 20,
    db: Session = Depends(get_db)
):
    """
    List all job postings with optional filters
    Query parameters:
    - location: Filter by location
    - job_type: Filter by job type (full-time, part-time, etc.)
    - status: Filter by status (default: active)
    - skip: Pagination offset
    - limit: Number of results per page
    """
    query = db.query(Job)
    
    if location:
        query = query.filter(Job.location.ilike(f"%{location}%"))
    
    if job_type:
        query = query.filter(Job.job_type == job_type)
    
    if status:
        query = query.filter(Job.status == status)
    
    jobs = query.order_by(Job.created_at.desc()).offset(skip).limit(limit).all()
    
    return [JobResponse.from_orm(job) for job in jobs]

@router.get("/{job_id}", response_model=JobResponse)
def get_job(job_id: int, db: Session = Depends(get_db)):
    """
    Get a specific job posting by ID
    """
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    return JobResponse.from_orm(job)

@router.put("/{job_id}", response_model=JobResponse)
def update_job(
    job_id: int,
    job_data: JobCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Update a job posting (employer only)
    """
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    # Verify ownership
    employer = db.query(Employer).filter(Employer.email == current_user.email).first()
    if not employer or job.employer_id != employer.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only update your own job postings"
        )
    
    # Update fields
    job.title = job_data.title
    job.description = job_data.description
    job.location = job_data.location
    job.salary_min = job_data.salary_min
    job.salary_max = job_data.salary_max
    job.job_type = job_data.job_type
    job.updated_at = datetime.utcnow()
    
    # Update skills if provided
    if job_data.skills_required is not None:
        # Remove existing skills
        db.query(JobSkill).filter(JobSkill.job_id == job_id).delete()
        
        # Add new skills
        for skill_id in job_data.skills_required:
            skill = db.query(Skill).filter(Skill.id == skill_id).first()
            if not skill:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Skill with ID {skill_id} not found"
                )
            
            job_skill = JobSkill(job_id=job_id, skill_id=skill_id)
            db.add(job_skill)
    
    db.commit()
    db.refresh(job)
    
    return JobResponse.from_orm(job)

@router.delete("/{job_id}", status_code=204)
def delete_job(
    job_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Close/delete a job posting (employer only)
    """
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    # Verify ownership
    employer = db.query(Employer).filter(Employer.email == current_user.email).first()
    if not employer or job.employer_id != employer.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only delete your own job postings"
        )
    
    # Close job instead of deleting
    job.status = "closed"
    job.updated_at = datetime.utcnow()
    db.commit()

@router.post("/{job_id}/close")
def close_job(
    job_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Close a job posting (employer only)
    """
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    # Verify ownership
    employer = db.query(Employer).filter(Employer.email == current_user.email).first()
    if not employer or job.employer_id != employer.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only close your own job postings"
        )
    
    job.status = "closed"
    job.updated_at = datetime.utcnow()
    db.commit()
    
    return {"message": "Job posting closed", "job_id": job_id}

@router.get("/{job_id}/applicants")
def get_job_applicants(
    job_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get all applicants for a specific job (employer only)
    """
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    # Verify ownership
    employer = db.query(Employer).filter(Employer.email == current_user.email).first()
    if not employer or job.employer_id != employer.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only view applicants for your own job postings"
        )
    
    from models import Application
    applications = db.query(Application).filter(
        Application.job_id == job_id
    ).order_by(Application.match_score.desc()).all()
    
    return {
        "job_id": job_id,
        "job_title": job.title,
        "total_applicants": len(applications),
        "applicants": [
            {
                "id": app.id,
                "user_id": app.user_id,
                "status": app.status,
                "match_score": app.match_score,
                "applied_at": app.created_at
            }
            for app in applications
        ]
    }
