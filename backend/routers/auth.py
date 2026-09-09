from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from passlib.context import CryptContext
from jose import JWTError, jwt
from typing import Optional
import os

from models import User, Employer
from schemas import UserRegister, UserLogin, UserResponse, TokenResponse, EmployerRegister, EmployerResponse
from main import get_db

router = APIRouter()

# Security Configuration
SECRET_KEY = os.getenv("JWT_SECRET", "your-secret-key-change-this-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRATION_HOURS", 24)) * 60

# Password hashing
pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__rounds=12  # Strong hashing rounds
)

# OAuth2 scheme
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

# ============ Utility Functions ============

def hash_password(password: str) -> str:
    """Hash password using bcrypt with 12 rounds"""
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters long")
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password against hash"""
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create JWT token with expiration"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    """Verify JWT token and get current user"""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: int = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise credentials_exception
    
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    
    return user

# ============ User Registration & Login ============

@router.post("/register", response_model=TokenResponse, status_code=201)
def register_user(
    user_data: UserRegister,
    db: Session = Depends(get_db)
):
    """
    Register a new job seeker
    Requirements:
    - Email must be unique
    - Password must be at least 8 characters
    """
    # Check if user already exists
    existing_user = db.query(User).filter(User.email == user_data.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    # Validate password strength
    if len(user_data.password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 8 characters long"
        )
    
    # Create new user with hashed password
    hashed_password = hash_password(user_data.password)
    db_user = User(
        email=user_data.email,
        password_hash=hashed_password,
        full_name=user_data.full_name,
        phone=user_data.phone,
        location=user_data.location,
        is_active=True
    )
    
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    
    # Create access token
    access_token = create_access_token(data={"sub": db_user.id})
    
    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        user=UserResponse.from_orm(db_user)
    )

@router.post("/login", response_model=TokenResponse)
def login_user(
    user_data: UserLogin,
    db: Session = Depends(get_db)
):
    """
    Login with email and password
    Returns JWT token for authenticated requests
    """
    user = db.query(User).filter(User.email == user_data.email).first()
    
    if not user or not verify_password(user_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User account is inactive"
        )
    
    # Create access token
    access_token = create_access_token(data={"sub": user.id})
    
    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        user=UserResponse.from_orm(user)
    )

# ============ Employer Registration & Login ============

@router.post("/employer/register", response_model=dict, status_code=201)
def register_employer(
    employer_data: EmployerRegister,
    db: Session = Depends(get_db)
):
    """
    Register a new employer/company
    """
    # Check if employer already exists
    existing_employer = db.query(Employer).filter(
        Employer.email == employer_data.email
    ).first()
    if existing_employer:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    # Validate password
    if len(employer_data.password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 8 characters long"
        )
    
    # Create new employer
    hashed_password = hash_password(employer_data.password)
    db_employer = Employer(
        company_name=employer_data.company_name,
        email=employer_data.email,
        password_hash=hashed_password,
        contact_person=employer_data.contact_person,
        phone=employer_data.phone,
        location=employer_data.location,
        is_active=True
    )
    
    db.add(db_employer)
    db.commit()
    db.refresh(db_employer)
    
    # Create access token
    access_token = create_access_token(data={"sub": f"employer_{db_employer.id}"})
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "employer": {
            "id": db_employer.id,
            "company_name": db_employer.company_name,
            "email": db_employer.email,
            "contact_person": db_employer.contact_person,
            "location": db_employer.location
        }
    }

@router.post("/employer/login")
def login_employer(
    email: str,
    password: str,
    db: Session = Depends(get_db)
):
    """
    Login employer with email and password
    """
    employer = db.query(Employer).filter(Employer.email == email).first()
    
    if not employer or not verify_password(password, employer.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not employer.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Employer account is inactive"
        )
    
    # Create access token
    access_token = create_access_token(data={"sub": f"employer_{employer.id}"})
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "employer": {
            "id": employer.id,
            "company_name": employer.company_name,
            "email": employer.email
        }
    }

# ============ Password Management ============

@router.post("/change-password")
def change_password(
    old_password: str,
    new_password: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Change user password (requires old password verification)
    """
    # Verify old password
    if not verify_password(old_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect password"
        )
    
    # Validate new password
    if len(new_password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 8 characters long"
        )
    
    # Update password
    current_user.password_hash = hash_password(new_password)
    db.commit()
    
    return {"message": "Password successfully changed"}

# ============ User Profile ============

@router.get("/me", response_model=UserResponse)
def get_current_user_profile(current_user: User = Depends(get_current_user)):
    """
    Get current authenticated user's profile
    """
    return UserResponse.from_orm(current_user)

@router.put("/profile")
def update_user_profile(
    full_name: Optional[str] = None,
    phone: Optional[str] = None,
    location: Optional[str] = None,
    bio: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Update user profile information
    """
    if full_name:
        current_user.full_name = full_name
    if phone:
        current_user.phone = phone
    if location:
        current_user.location = location
    if bio:
        current_user.bio = bio
    
    current_user.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(current_user)
    
    return UserResponse.from_orm(current_user)

# ============ Account Deactivation ============

@router.post("/deactivate")
def deactivate_account(
    password: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Deactivate user account (requires password verification)
    """
    # Verify password
    if not verify_password(password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect password"
        )
    
    # Deactivate account
    current_user.is_active = False
    db.commit()
    
    return {"message": "Account successfully deactivated"}
