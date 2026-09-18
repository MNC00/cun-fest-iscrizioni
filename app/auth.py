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


def create_session_token(username: str, is_admin: bool = False) -> str:
    """Crea un token di sessione firmato contenente username e ruolo dell'operatore."""
    return _serializer.dumps({"username": username, "is_admin": is_admin})


def read_session_token(token: str) -> dict | None:
    """Verifica il token di sessione e restituisce {"username", "is_admin"}, o None se non valido/scaduto."""
    try:
        data = _serializer.loads(token, max_age=SESSION_MAX_AGE_SECONDS)
    except (BadSignature, SignatureExpired):
        return None
    return data


def get_current_operatore_username(request) -> str | None:
    """Legge il cookie di sessione dalla request e restituisce lo username loggato, o None."""
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        return None
    data = read_session_token(token)
    return data.get("username") if data else None


def get_current_operatore_is_admin(request) -> bool:
    """True se l'operatore loggato ha il ruolo di amministratore.

    Il ruolo è letto dal token di sessione firmato (impostato al login):
    se il ruolo di un operatore cambia mentre è già loggato, il cambiamento
    ha effetto dal login successivo (la sessione dura al massimo 8 ore).
    """
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        return False
    data = read_session_token(token)
    return bool(data and data.get("is_admin"))
