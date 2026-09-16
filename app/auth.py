import os

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from passlib.context import CryptContext

SECRET_KEY = os.getenv("SECRET_KEY", "cunfest-insecure-default-key")
SESSION_COOKIE_NAME = "session"
SESSION_MAX_AGE_SECONDS = 60 * 60 * 8  # 8 ore

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
_serializer = URLSafeTimedSerializer(SECRET_KEY, salt="operatore-session")


def hash_password(password: str) -> str:
    """Genera l'hash bcrypt di una password."""
    return pwd_context.hash(password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    """Verifica una password in chiaro contro il suo hash bcrypt."""
    return pwd_context.verify(plain_password, password_hash)


def create_session_token(username: str) -> str:
    """Crea un token di sessione firmato contenente lo username dell'operatore."""
    return _serializer.dumps({"username": username})


def read_session_token(token: str) -> str | None:
    """Verifica il token di sessione e restituisce lo username, o None se non valido/scaduto."""
    try:
        data = _serializer.loads(token, max_age=SESSION_MAX_AGE_SECONDS)
    except (BadSignature, SignatureExpired):
        return None
    return data.get("username")


def get_current_operatore_username(request) -> str | None:
    """Legge il cookie di sessione dalla request e restituisce lo username loggato, o None."""
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        return None
    return read_session_token(token)
