"""Copia le ricevute in una cartella Google Drive configurata dall'operatore."""
import json
import logging
import os

import httpx

logger = logging.getLogger(__name__)

TOKEN_URL = "https://oauth2.googleapis.com/token"
FILES_URL = "https://www.googleapis.com/drive/v3/files"
UPLOAD_URL = "https://www.googleapis.com/upload/drive/v3/files"


class DriveServiceError(Exception):
    """Errore applicativo durante la copia di una ricevuta su Google Drive."""


def _credenziali() -> tuple[str, str, str]:
    client_id = os.getenv("GMAIL_CLIENT_ID", "")
    client_secret = os.getenv("GMAIL_CLIENT_SECRET", "")
    refresh_token = os.getenv("GMAIL_REFRESH_TOKEN", "")
    if not client_id or not client_secret or not refresh_token:
        raise DriveServiceError(
            "Configura le credenziali OAuth Google e autorizza anche l'accesso Drive."
        )
    return client_id, client_secret, refresh_token


def _access_token() -> str:
    client_id, client_secret, refresh_token = _credenziali()
    try:
        risposta = httpx.post(
            TOKEN_URL,
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
            timeout=10.0,
        )
    except httpx.HTTPError as exc:
        raise DriveServiceError("Impossibile contattare Google per autorizzare Drive.") from exc

    if risposta.status_code >= 400:
        logger.error("Refresh token Google Drive rifiutato (status %s).", risposta.status_code)
        raise DriveServiceError("Autorizzazione Google Drive non valida o revocata.")

    token = risposta.json().get("access_token")
    if not token:
        raise DriveServiceError("Google non ha restituito un token per Drive.")
    return token


def crea_cartella_ricevute() -> str:
    """Crea una cartella privata dell'app, da condividere poi dall'interfaccia Drive."""
    token = _access_token()
    try:
        risposta = httpx.post(
            FILES_URL,
            headers={"Authorization": f"Bearer {token}"},
            json={"name": "Ricevute CUN Fest", "mimeType": "application/vnd.google-apps.folder"},
            params={"fields": "id"},
            timeout=15.0,
        )
    except httpx.HTTPError as exc:
        raise DriveServiceError("Impossibile creare la cartella su Google Drive.") from exc

    if risposta.status_code >= 400:
        logger.error("Creazione cartella Google Drive fallita (status %s).", risposta.status_code)
        raise DriveServiceError("Google Drive non ha creato la cartella delle ricevute.")

    folder_id = risposta.json().get("id")
    if not folder_id:
        raise DriveServiceError("Google Drive non ha restituito l'ID della cartella.")
    return folder_id


def carica_ricevuta_drive(nome_file: str, contenuto: bytes, content_type: str) -> str:
    """Carica una ricevuta nella cartella configurata e restituisce l'ID Drive."""
    folder_id = os.getenv("GOOGLE_DRIVE_FOLDER_ID", "").strip()
    if not folder_id:
        raise DriveServiceError("Configura GOOGLE_DRIVE_FOLDER_ID per attivare la copia su Drive.")

    token = _access_token()
    metadata = json.dumps({"name": nome_file, "parents": [folder_id]})
    try:
        risposta = httpx.post(
            UPLOAD_URL,
            params={"uploadType": "multipart", "supportsAllDrives": "true", "fields": "id"},
            headers={"Authorization": f"Bearer {token}"},
            files={
                "metadata": (None, metadata, "application/json; charset=UTF-8"),
                "file": (nome_file, contenuto, content_type or "application/octet-stream"),
            },
            timeout=30.0,
        )
    except httpx.HTTPError as exc:
        raise DriveServiceError("Errore di rete durante la copia della ricevuta su Drive.") from exc

    if risposta.status_code >= 400:
        logger.error("Upload Google Drive fallito (status %s).", risposta.status_code)
        raise DriveServiceError("Google Drive non ha accettato la ricevuta.")

    file_id = risposta.json().get("id")
    if not file_id:
        raise DriveServiceError("Google Drive non ha restituito l'ID della ricevuta caricata.")
    return file_id