"""Upload/download dei file (ricevute di pagamento) su Supabase Storage.

Il progetto usa già Supabase per il database Postgres: Supabase Storage è lo
storage di file associato allo stesso account/progetto (incluso gratis nel
piano free, ~1GB) ed è la scelta naturale per salvare le ricevute in modo
persistente. Render (piano free) ha infatti un filesystem effimero: qualsiasi
file salvato sul disco locale del server verrebbe perso al primo riavvio.

Le chiamate usano l'API REST di Supabase Storage via HTTPS (stesso pattern
di app/email_service.py per la Gmail API): nessuna libreria aggiuntiva
necessaria, solo httpx (già una dipendenza del progetto).

Richiede le variabili d'ambiente:
- SUPABASE_URL: URL del progetto Supabase, es. "https://xxxx.supabase.co".
- SUPABASE_SERVICE_ROLE_KEY: service role key del progetto (Project Settings
  → API su Supabase). NON è l'anon key: la service role key bypassa le regole
  di Row Level Security ed è necessaria perché qui è il server (non l'utente
  finale) a caricare/scaricare i file. Va trattata come un segreto.
- SUPABASE_STORAGE_BUCKET (opzionale, default "ricevute-pagamento"): nome del
  bucket di Storage. Va creato una tantum su Supabase (Storage → New bucket),
  come bucket PRIVATO (non pubblico): l'accesso ai file avviene solo tramite
  questo modulo, autenticato con la service role key.
"""
import logging
import os

import httpx

logger = logging.getLogger(__name__)

DEFAULT_BUCKET = "ricevute-pagamento"


class StorageServiceError(Exception):
    """Errore applicativo nell'upload/download di un file su Supabase Storage."""


def _config() -> tuple[str, str, str]:
    supabase_url = os.getenv("SUPABASE_URL", "").rstrip("/")
    service_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    bucket = os.getenv("SUPABASE_STORAGE_BUCKET", DEFAULT_BUCKET)
    if not supabase_url or not service_key:
        raise StorageServiceError(
            "SUPABASE_URL e SUPABASE_SERVICE_ROLE_KEY devono essere configurate come variabili d'ambiente."
        )
    return supabase_url, service_key, bucket


def carica_file(path: str, contenuto: bytes, content_type: str) -> None:
    """Carica (o sovrascrive, se esiste già) un file su Supabase Storage al percorso indicato."""
    supabase_url, service_key, bucket = _config()

    try:
        risposta = httpx.post(
            f"{supabase_url}/storage/v1/object/{bucket}/{path}",
            headers={
                "Authorization": f"Bearer {service_key}",
                "apikey": service_key,
                "Content-Type": content_type or "application/octet-stream",
                "x-upsert": "true",
            },
            content=contenuto,
            timeout=30.0,
        )
    except httpx.HTTPError as exc:
        logger.error("Errore di rete nell'upload su Supabase Storage (%s): %s", path, exc)
        raise StorageServiceError(f"Upload fallito: errore di rete verso Supabase Storage ({exc})") from exc

    if risposta.status_code >= 400:
        logger.error(
            "Supabase Storage ha rifiutato l'upload di %s (status %s): %s", path, risposta.status_code, risposta.text
        )
        raise StorageServiceError(
            f"Upload fallito: Supabase Storage ha risposto con errore {risposta.status_code} ({risposta.text})"
        )


def scarica_file(path: str) -> tuple[bytes, str]:
    """Scarica un file da Supabase Storage. Ritorna (contenuto, content_type)."""
    supabase_url, service_key, bucket = _config()

    try:
        risposta = httpx.get(
            f"{supabase_url}/storage/v1/object/{bucket}/{path}",
            headers={
                "Authorization": f"Bearer {service_key}",
                "apikey": service_key,
            },
            timeout=30.0,
        )
    except httpx.HTTPError as exc:
        logger.error("Errore di rete nel download da Supabase Storage (%s): %s", path, exc)
        raise StorageServiceError(f"Download fallito: errore di rete verso Supabase Storage ({exc})") from exc

    if risposta.status_code >= 400:
        logger.error(
            "Supabase Storage ha rifiutato il download di %s (status %s): %s", path, risposta.status_code, risposta.text
        )
        raise StorageServiceError(
            f"Download fallito: Supabase Storage ha risposto con errore {risposta.status_code} ({risposta.text})"
        )

    content_type = risposta.headers.get("content-type", "application/octet-stream")
    return risposta.content, content_type


def elimina_file(path: str) -> None:
    """Elimina un file da Supabase Storage. Non solleva errore se il file non esiste già."""
    supabase_url, service_key, bucket = _config()

    try:
        risposta = httpx.delete(
            f"{supabase_url}/storage/v1/object/{bucket}/{path}",
            headers={
                "Authorization": f"Bearer {service_key}",
                "apikey": service_key,
            },
            timeout=30.0,
        )
    except httpx.HTTPError as exc:
        logger.error("Errore di rete nell'eliminazione da Supabase Storage (%s): %s", path, exc)
        raise StorageServiceError(f"Eliminazione fallita: errore di rete verso Supabase Storage ({exc})") from exc

    if risposta.status_code >= 400 and risposta.status_code != 404:
        logger.error(
            "Supabase Storage ha rifiutato l'eliminazione di %s (status %s): %s",
            path,
            risposta.status_code,
            risposta.text,
        )
        raise StorageServiceError(
            f"Eliminazione fallita: Supabase Storage ha risposto con errore {risposta.status_code} ({risposta.text})"
        )
