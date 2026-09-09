from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime

# ============ Authentication Schemas ============
class UserRegister(BaseModel):
    email: EmailStr
    password: str
    full_name: str
    phone: Optional[str] = None
    location: Optional[str] = None

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserResponse(BaseModel):
    id: int
    email: str
    full_name: str
    phone: Optional[str]
    location: Optional[str]
    account_balance_zar: float
    loyalty_points: int
    debit_card_linked: bool
    created_at: datetime
    
    class Config:
        from_attributes = True

class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    user: UserResponse

# ============ Job Schemas ============
class SkillCreate(BaseModel):
    name: str
    category: Optional[str] = None

class SkillResponse(BaseModel):
    id: int
    name: str
    category: Optional[str]
    
    class Config:
        from_attributes = True

class JobCreate(BaseModel):
    title: str
    description: str
    location: Optional[str] = None
    salary_min: Optional[float] = None
    salary_max: Optional[float] = None
    job_type: Optional[str] = None
    skills_required: Optional[list[int]] = None  # Skill IDs

class JobResponse(BaseModel):
    id: int
    title: str
    description: str
    location: Optional[str]
    salary_min: Optional[float]
    salary_max: Optional[float]
    job_type: Optional[str]
    status: str
    skills_required: list[SkillResponse] = []
    created_at: datetime
    
    class Config:
        from_attributes = True

class UserSkillCreate(BaseModel):
    skill_id: int
    proficiency_level: Optional[str] = "beginner"

# ============ Application Schemas ============
class ApplicationCreate(BaseModel):
    job_id: int
    cover_letter: Optional[str] = None

class ApplicationResponse(BaseModel):
    id: int
    job_id: int
    user_id: int
    cover_letter: Optional[str]
    status: str
    match_score: Optional[float]
    created_at: datetime
    
    class Config:
        from_attributes = True

# ============ Payment & Loyalty Schemas ============
class PaymentRequest(BaseModel):
    user_id: int
    amount_zar: float
    payment_method: Optional[str] = "debit_card"

class PaymentResponse(BaseModel):
    id: Optional[int] = None
    user_id: int
    amount_zar: float
    status: str
    payment_method: str
    transaction_id: str
    scheduled_for: Optional[datetime] = None
    processed_at: Optional[datetime] = None
    message: Optional[str] = None
    
    class Config:
        from_attributes = True

class LoyaltyPointsResponse(BaseModel):
    id: int
    user_id: int
    points: int
    reason: str
    transaction_id: str
    created_at: datetime
    
    class Config:
        from_attributes = True

class BalanceResponse(BaseModel):
    user_id: int
    account_balance_zar: float
    loyalty_points: int
    debit_card_linked: bool
    currency: str = "ZAR"

class DebitCardResponse(BaseModel):
    user_id: int
    debit_card_linked: bool
    message: str

# ============ Matching Schemas ============
class MatchResponse(BaseModel):
    job_id: int
    match_score: float
    reason: Optional[str]
    job: JobResponse
    
    class Config:
        from_attributes = True

# ============ Employer Schemas ============
class EmployerRegister(BaseModel):
    company_name: str
    email: EmailStr
    password: str
    contact_person: str
    phone: str
    location: str

class EmployerResponse(BaseModel):
    id: int
    company_name: str
    email: str
    contact_person: str
    phone: str
    location: str
    company_description: Optional[str]
    created_at: datetime
    
    class Config:
        from_attributes = True
