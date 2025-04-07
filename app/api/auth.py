from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, status, Request, Form
from sqlalchemy.orm import Session
from passlib.context import CryptContext
from datetime import timedelta, datetime
from jose import jwt, JWTError
from random import randint
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
import logging
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.config import settings
from app.db.models import User, TempUser, PasswordReset
from app.utils.mail import send_verification_email, send_recovery_email
from app.schemas.user import UserCreate, UserLogin, UserOut, VerifyRequest, PasswordResetRequest, PasswordResetConfirm

# Настройка логирования
logger = logging.getLogger(__name__)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
router = APIRouter()

# Настройки JWT
SECRET_KEY = settings.SECRET_KEY
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = settings.ACCESS_TOKEN_EXPIRE_MINUTES

# Схема OAuth2 для аутентификации
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(data: dict, expires_delta: timedelta = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(days=7))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db)
) -> User:
    """Получает текущего пользователя из JWT токена."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
        
    result = await db.execute(
        select(User).where(User.email == email)
    )
    user = result.scalar_one_or_none()
    
    if user is None:
        raise credentials_exception
    return user

@router.post("/register")
async def register_user(
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    email: str = Form(...),
    first_name: str = Form(...),
    last_name: str = Form(...),
    password: str = Form(...)
):
    """Регистрация нового пользователя."""
    # Проверяем существование пользователя
    result = await db.execute(
        select(User).where(User.email == email)
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email уже зарегистрирован")

    # Создаем временного пользователя
    verification_code = randint(100000, 999999)
    temp_user = TempUser(
        email=email,
        verification_code=verification_code,
        first_name=first_name,
        last_name=last_name,
        hashed_password=get_password_hash(password)
    )
    
    db.add(temp_user)
    await db.commit()
    await db.refresh(temp_user)

    # Отправляем код подтверждения
    background_tasks.add_task(send_verification_email, email, verification_code)
    
    return {"message": "Код подтверждения отправлен на вашу почту"}

@router.post("/verify")
async def verify_code(
    request: VerifyRequest,
    db: AsyncSession = Depends(get_db)
):
    """Подтверждение кода верификации."""
    # Находим временного пользователя
    result = await db.execute(
        select(TempUser).where(
            TempUser.email == request.email,
            TempUser.verification_code == request.code,
            TempUser.is_used == False
        )
    )
    temp_user = result.scalar_one_or_none()
    
    if not temp_user:
        raise HTTPException(status_code=400, detail="Неверный или истёкший код подтверждения")

    # Создаем постоянного пользователя
    user = User(
        email=temp_user.email,
        hashed_password=temp_user.hashed_password,
        first_name=temp_user.first_name,
        last_name=temp_user.last_name,
        is_active=True,
        is_verified=True
    )
    
    db.add(user)
    
    # Отмечаем временного пользователя как использованного
    temp_user.is_used = True
    
    await db.commit()
    await db.refresh(user)

    # Создаем токен доступа
    access_token = create_access_token(data={"sub": user.email, "user_id": user.id})
    
    return {"access_token": access_token, "token_type": "bearer"}

@router.post("/login")
async def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db)
):
    """Авторизация пользователя."""
    try:
        logger.info(f"Login attempt for user: {form_data.username}")
        logger.info(f"Request headers: {request.headers}")
        
        # Используем async execute вместо query
        result = await db.execute(
            select(User).where(User.email == form_data.username)
        )
        db_user = result.scalar_one_or_none()
        
        if not db_user:
            logger.warning(f"User not found: {form_data.username}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Неверный email или пароль",
                headers={"WWW-Authenticate": "Bearer"},
            )
            
        if not verify_password(form_data.password, db_user.hashed_password):
            logger.warning(f"Invalid password for user: {form_data.username}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Неверный email или пароль",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        if not db_user.is_verified:
            logger.warning(f"Unverified user attempt to login: {form_data.username}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Пользователь не верифицирован"
            )
        
        # Обновляем is_active
        db_user.is_active = True
        await db.commit()
        await db.refresh(db_user)

        access_token = create_access_token(data={"sub": db_user.email, "user_id": db_user.id})
        logger.info(f"Login successful for user: {form_data.username}")
        
        return {"access_token": access_token, "token_type": "bearer"}
    except Exception as e:
        logger.error(f"Login error for user {form_data.username}: {str(e)}")
        raise

@router.get("/profile", response_model=UserOut)
async def get_profile(
    current_user: User = Depends(get_current_user)
):
    """Получение профиля текущего пользователя."""
    return current_user

@router.post("/forgot-password")
async def forgot_password(
    request: PasswordResetRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    """Запрос на восстановление пароля."""
    result = await db.execute(
        select(User).where(User.email == request.email)
    )
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь с таким email не найден")

    # Генерация кода восстановления
    reset_code = randint(100000, 999999)
    password_reset = PasswordReset(email=request.email, code=reset_code)
    db.add(password_reset)
    await db.commit()

    # Отправка кода на email
    background_tasks.add_task(send_recovery_email, request.email, reset_code)

    return {"message": "Код восстановления отправлен на вашу почту"}

@router.post("/reset-password")
async def reset_password(
    request: PasswordResetConfirm,
    db: AsyncSession = Depends(get_db)
):
    """Подтверждение кода и изменение пароля."""
    result = await db.execute(
        select(PasswordReset).where(
            PasswordReset.email == request.email,
            PasswordReset.code == request.code,
            PasswordReset.is_used == False
        )
    )
    reset_entry = result.scalar_one_or_none()

    if not reset_entry:
        raise HTTPException(status_code=400, detail="Неверный или истёкший код восстановления")

    # Найти пользователя
    result = await db.execute(
        select(User).where(User.email == request.email)
    )
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь с таким email не найден")

    # Изменить пароль пользователя
    user.hashed_password = get_password_hash(request.new_password)
    
    # Отметить код как использованный
    reset_entry.is_used = True
    
    await db.commit()

    return {"message": "Пароль успешно изменён"}

@router.post("/logout")
async def logout():
    """Выход из системы."""
    return {"message": "Выход успешно выполнен"}
