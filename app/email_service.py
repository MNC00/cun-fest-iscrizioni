"""Costruzione e invio delle email del CUN Fest.

I contenuti (testo, struttura, formulazioni) replicano fedelmente quelli del
vecchio sistema (Google Apps Script, Domain/Email.js): stesso IBAN, stesso
paragrafo pagamento, stesse varianti "solo pranzo CUN" / prezzo noto o meno.
L'invio vero e proprio avviene tramite la Gmail API di Google via HTTPS
(OAuth2, non SMTP): l'email risulta autenticata come l'account Gmail
configurato (nessun problema di spam/DMARC) e non serve alcuna porta SMTP,
quindi funziona anche sui piani gratuiti di hosting (es. Render) che
bloccano il traffico in uscita sulle porte 25/465/587.
"""
import base64
import logging
import os
import re
from datetime import date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Iterable

import httpx

logger = logging.getLogger(__name__)

GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GMAIL_SEND_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"

LINK_SITO_CUNFEST = "https://sites.google.com/view/pgstimm/cunfest?authuser=0"
IBAN_CUNFEST = "IT87W0200859280000003853446"
INTESTATARIO_CUNFEST = "SCUOLA APOSTOLICA BERTONI"


_MESI_ITALIANO = [
    "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
    "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre",
]
_GIORNI_ITALIANO = [
    "lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica",
]

_LABEL_PASTO = {
    "nessuno": "Nessuno",
    "colazione": "Colazione",
    "pranzo": "Pranzo",
    "cena": "Cena",
    "dopo_cena": "Dopo cena",
    "prima_colazione": "Prima di colazione",
}


class EmailServiceError(Exception):
    """Errore applicativo nell'invio di una email tramite SMTP."""


# --------------------------------------------------------------------------
# Formattazione dati
# --------------------------------------------------------------------------

def formatta_data_italiana(d: date | None) -> str:
    """Formatta una data come "lunedì 15 agosto 2026", senza dipendere dal locale di sistema."""
    if not d:
        return "-"
    return f"{_GIORNI_ITALIANO[d.weekday()]} {d.day} {_MESI_ITALIANO[d.month - 1]} {d.year}"


def formatta_pasto(codice: str | None) -> str:
    """Converte il codice di un pasto (es. 'dopo_cena') nella sua etichetta leggibile."""
    return _LABEL_PASTO.get(codice or "nessuno", "Nessuno")


# --------------------------------------------------------------------------
# Blocchi HTML riutilizzati tra le varie email (fedeli al vecchio Email.js)
# --------------------------------------------------------------------------

def _html_a_testo(html: str) -> str:
    """Rimuove i tag HTML per ottenere una versione testuale approssimativa del corpo email."""
    testo = re.sub(r"</(p|li|ul|br)>", "\n", html, flags=re.IGNORECASE)
    testo = re.sub(r"<br\s*/?>", "\n", testo, flags=re.IGNORECASE)
    testo = re.sub(r"<[^>]+>", "", testo)
    testo = testo.replace("&nbsp;", " ")
    testo = re.sub(r"\n{3,}", "\n\n", testo)
    return testo.strip()


def _paragrafo_pagamento() -> str:
    return (
        f"<p>È consigliato effettuare il pagamento tramite bonifico su C/C <b>{INTESTATARIO_CUNFEST}</b>.</p>"
        f"<p><b>IBAN:</b> {IBAN_CUNFEST}<br>"
        "<b>Causale:</b> “Pre CUN e CUN Fest - nome del partecipante e codice fiscale”.</p>"
        "<p>Nel caso facessi il bonifico, rispondi a questa mail allegando la ricevuta.</p>"
    )


def _paragrafo_pagamento_solo_pranzo_conferma_con_prezzo() -> str:
    """Variante storica usata SOLO nella conferma iniziale, ramo 'solo pranzo CUN' con prezzo noto."""
    return (
        f"<p>È consigliato effettuare il pagamento tramite bonifico su C/C <b>{INTESTATARIO_CUNFEST}</b>.</p>"
        f"<p><b>IBAN:</b> {IBAN_CUNFEST}<br>"
        "<b>Causale:</b> “Pre CUN e CUN Fest - nome del partecipante e codice fiscale.”</p>"
    )


def _paragrafo_chiusura() -> str:
    return (
        "<p>Per qualsiasi domanda, contattaci e cercheremo di risponderti nel minor tempo possibile.</p>"
        f"<p>Per ulteriori informazioni, visita il <a href='{LINK_SITO_CUNFEST}'>sito del CUNFest</a>.</p>"
        "<br><p>Grazie e a presto.</p><p>Gruppo Iscrizioni</p>"
    )


def _paragrafo_chiusura_aggiornamento() -> str:
    """Variante storica usata SOLO nell'email di aggiornamento prezzo."""
    return (
        "<p>Per qualsiasi domanda, contattaci: cercheremo di risponderti nel minor tempo possibile.</p>"
        f"<p>Per info, visita il <a href='{LINK_SITO_CUNFEST}'>sito del CUNFest</a>.</p>"
        "<p>Grazie e a presto.</p><p>Gruppo Iscrizioni</p>"
    )


def _riepilogo_soggiorno(contesto: dict) -> str:
    return (
        "<p>Di seguito, il riepilogo della durata della tua permanenza:</p>"
        "<ul>"
        f"<li>Data di arrivo: {contesto['dataArrivoFormattata']}</li>"
        f"<li>Pasto di arrivo: {contesto['pastoArrivo']}</li>"
        f"<li>Data di partenza: {contesto['dataPartenzaFormattata']}</li>"
        f"<li>Pasto di partenza: {contesto['pastoPartenza']}</li>"
        "</ul>"
    )


def _riepilogo_soggiorno_aggiornamento(contesto: dict) -> str:
    """Variante storica usata SOLO nell'email di aggiornamento prezzo."""
    return (
        "<p>Di seguito il riepilogo della tua permanenza:</p>"
        "<ul>"
        f"<li>Data di arrivo: {contesto['dataArrivoFormattata']}</li>"
        f"<li>Pasto di arrivo: {contesto['pastoArrivo']}</li>"
        f"<li>Data di partenza: {contesto['dataPartenzaFormattata']}</li>"
        f"<li>Pasto di partenza: {contesto['pastoPartenza']}</li>"
        "</ul>"
    )


def _paragrafo_annullamento(link: str) -> str:
    return (
        "<p style='font-size:0.9em;color:#555'>Se non potrai più partecipare, puoi annullare la tua "
        f"iscrizione in autonomia da questo link: <a href='{link}'>Annulla la mia iscrizione</a>.</p>"
    )


def _testo_libero_a_html(testo_libero: str) -> str:
    """Converte un testo libero in HTML preservando i paragrafi (riga vuota = nuovo paragrafo)."""
    if not testo_libero:
        return ""
    normalizzato = testo_libero.replace("\r\n", "\n").strip()
    if not normalizzato:
        return ""
    paragrafi = [p for p in re.split(r"\n\s*\n", normalizzato) if p.strip()]
    return "".join(f"<p>{p.replace(chr(10), '<br>')}</p>" for p in paragrafi)


# --------------------------------------------------------------------------
# Costruzione email (pura: nessun invio, restituisce {oggetto, html, testo})
# --------------------------------------------------------------------------

def costruisci_email_conferma(contesto: dict) -> dict:
    """Email di conferma iscrizione (primo invio, dal form).

    contesto: nome, anno, hasPrezzo, isSoloPranzo, dataArrivoFormattata,
    pastoArrivo, dataPartenzaFormattata, pastoPartenza, prezzo (opz.),
    linkAnnullamento (opz.).
    """
    oggetto = "Conferma Iscrizione CUN Fest"
    nome = contesto["nome"]
    anno = contesto["anno"]

    if contesto.get("isSoloPranzo"):
        if contesto.get("hasPrezzo"):
            html = (
                f"<p>Ciao {nome}!</p>"
                f"<p>Abbiamo ricevuto la tua iscrizione al pranzo del CUN Fest {anno} e siamo contenti che parteciperai.</p>"
                f"<p>Il costo dell'esperienza è pari a: €{contesto['prezzo']}.</p>"
                "<p>Qualora dovessi saltare dei pasti o per qualsiasi altro aspetto connesso alla questione prezzo, "
                "ti saremmo grati se potessi farcelo sapere rispondendo a questa email.</p>"
                + _paragrafo_pagamento_solo_pranzo_conferma_con_prezzo()
                + _paragrafo_chiusura()
            )
        else:
            html = (
                f"<p>Ciao {nome}!</p>"
                f"<p>Abbiamo ricevuto la tua iscrizione al pranzo del CUN Fest {anno} e siamo contenti che parteciperai.</p>"
                "<p>Purtroppo, al momento non ci sono stati comunicati i prezzi dell'esperienza da parte della gestione "
                "della casa. Non appena ci saranno novità, sarai informato.</p>"
                + _paragrafo_chiusura()
            )
    else:
        if contesto.get("hasPrezzo"):
            html = (
                f"<p>Ciao {nome}!</p>"
                f"<p>Abbiamo ricevuto la tua iscrizione al CUN Fest {anno} e siamo contenti che parteciperai.</p>"
                + _riepilogo_soggiorno(contesto)
                + f"<p>Il costo dell'esperienza è pari a: €{contesto['prezzo']}.</p>"
                "<p>Tieni presente che questi prezzi sono calcolati sulla base delle date fornite nella compilazione "
                "del form. Inoltre, ricordiamo che il prezzo è calcolato fino al pranzo del CUN; per quanto riguarda i "
                "giorni/pasti successivi, bisognerà prendere accordi con la casa. Qualora dovessi saltare dei pasti o "
                "per qualsiasi altro aspetto connesso alla questione prezzo, ti saremmo grati se potessi farcelo sapere "
                "rispondendo a questa email.</p>"
                + _paragrafo_pagamento()
                + _paragrafo_chiusura()
            )
        else:
            html = (
                f"<p>Ciao {nome}!</p>"
                f"<p>Abbiamo ricevuto la tua iscrizione al CUN Fest {anno} e siamo contenti che parteciperai.</p>"
                + _riepilogo_soggiorno(contesto)
                + "<p>Purtroppo, al momento non ci sono stati comunicati i prezzi dell'esperienza da parte della "
                "gestione della casa.</p>"
                "<p>Non appena ci saranno novità, sarai informato.</p>"
                + _paragrafo_chiusura()
            )

    if contesto.get("linkAnnullamento"):
        html += _paragrafo_annullamento(contesto["linkAnnullamento"])

    return {"oggetto": oggetto, "html": html, "testo": _html_a_testo(html)}


def costruisci_email_aggiornamento(contesto: dict) -> dict:
    """Email di aggiornamento prezzo (reinvio manuale). Stesso contesto di costruisci_email_conferma."""
    oggetto = "Aggiornamento prezzi CUN Fest"
    nome = contesto["nome"]
    anno = contesto["anno"]

    if contesto.get("isSoloPranzo"):
        html = (
            f"<p>Ciao {nome}!</p>"
            "<p>Abbiamo ricevuto dalla gestione della casa i prezzi aggiornati.</p>"
            + (
                f"<p>Il costo del <b>pranzo del CUN Fest {anno}</b> è pari a: <b>€{contesto.get('prezzo')}</b>.</p>"
                if contesto.get("hasPrezzo")
                else "<p>Al momento non è stato ancora comunicato il prezzo del pranzo. Ti avviseremo non appena disponibile.</p>"
            )
            + _paragrafo_pagamento()
            + _paragrafo_chiusura_aggiornamento()
        )
    else:
        html = (
            f"<p>Ciao {nome}!</p>"
            "<p>Abbiamo ricevuto dalla gestione della casa i prezzi aggiornati.</p>"
            + _riepilogo_soggiorno_aggiornamento(contesto)
            + (
                f"<p>Il costo dell'esperienza è pari a: <b>€{contesto.get('prezzo')}</b>.</p>"
                "<p>Tieni presente che questi prezzi sono calcolati sulle date indicate nel form. Inoltre, ricordiamo "
                "che il prezzo è calcolato fino al pranzo del CUN; per quanto riguarda i giorni/pasti successivi, "
                "bisognerà prendere accordi con la casa. Se dovessi saltare dei pasti o notassi incongruenze, "
                "rispondi a questa email per aggiornarci.</p>"
                if contesto.get("hasPrezzo")
                else "<p>Il prezzo aggiornato non è ancora disponibile per la tua permanenza. Ti avviseremo appena possibile.</p>"
            )
            + _paragrafo_pagamento()
            + _paragrafo_chiusura_aggiornamento()
        )

    if contesto.get("linkAnnullamento"):
        html += _paragrafo_annullamento(contesto["linkAnnullamento"])

    return {"oggetto": oggetto, "html": html, "testo": _html_a_testo(html)}


def costruisci_email_annullamento(contesto: dict) -> dict:
    """Email di conferma annullamento di una singola iscrizione. contesto: {nome}."""
    oggetto = "Iscrizione annullata - CUN Fest"
    nome = contesto["nome"]
    html = (
        f"<p>Ciao {nome}.</p>"
        "<p>Ti confermiamo che la tua iscrizione al CUN Fest è stata annullata come richiesto.</p>"
        "<p>Se si è trattato di un errore o hai cambiato idea, scrivici pure rispondendo a questa email: "
        "ti aiuteremo a reiscriverti.</p>"
        "<br><p>Grazie e a presto.</p><p>Gruppo Iscrizioni</p>"
    )
    return {"oggetto": oggetto, "html": html, "testo": _html_a_testo(html)}


def costruisci_email_annullamento_nucleo(contesto: dict) -> dict:
    """Email di recap per l'annullamento di un intero nucleo familiare in un'unica soluzione.

    contesto: {nomi: elenco dei nomi completi dei partecipanti annullati}.
    """
    oggetto = "Iscrizioni annullate - CUN Fest"
    nomi = contesto["nomi"]
    elenco = "".join(f"<li>{n}</li>" for n in nomi)
    html = (
        "<p>Ciao.</p>"
        "<p>Ti confermiamo che, come richiesto, sono state annullate tutte le iscrizioni del tuo nucleo familiare "
        "al CUN Fest:</p>"
        f"<ul>{elenco}</ul>"
        "<p>Se si è trattato di un errore o avete cambiato idea, scriveteci pure rispondendo a questa email: "
        "vi aiuteremo a reiscrivervi.</p>"
        "<br><p>Grazie e a presto.</p><p>Gruppo Iscrizioni</p>"
    )
    return {"oggetto": oggetto, "html": html, "testo": _html_a_testo(html)}


def costruisci_email_massa(nome: str, oggetto: str, testo_libero: str) -> dict:
    """Email per una comunicazione di massa personalizzata solo nel saluto."""
    html = (
        f"<p>Ciao {nome}!</p>"
        + _testo_libero_a_html(testo_libero)
        + "<p>A prestissimo!<br>Gruppo Iscrizioni.</p>"
    )
    return {"oggetto": oggetto, "html": html, "testo": _html_a_testo(html)}


# --------------------------------------------------------------------------
# Invio via Gmail API (OAuth2)
# --------------------------------------------------------------------------

def _ottieni_access_token() -> str:
    """Scambia il refresh token Google con un access token valido (via HTTPS).

    Richiede GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET, GMAIL_REFRESH_TOKEN,
    ottenuti una tantum con lo script scripts/gmail_oauth_setup.py.
    """
    client_id = os.getenv("GMAIL_CLIENT_ID")
    client_secret = os.getenv("GMAIL_CLIENT_SECRET")
    refresh_token = os.getenv("GMAIL_REFRESH_TOKEN")

    if not client_id or not client_secret or not refresh_token:
        raise EmailServiceError(
            "GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET e GMAIL_REFRESH_TOKEN devono essere "
            "configurate come variabili d'ambiente (vedi scripts/gmail_oauth_setup.py)."
        )

    try:
        risposta = httpx.post(
            GOOGLE_TOKEN_URL,
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
            timeout=10.0,
        )
    except httpx.HTTPError as exc:
        logger.error("Errore di rete nel refresh del token Gmail: %s", exc)
        raise EmailServiceError(f"Invio email fallito: impossibile contattare Google ({exc})") from exc

    if risposta.status_code >= 400:
        logger.error("Refresh del token Gmail fallito (status %s): %s", risposta.status_code, risposta.text)
        raise EmailServiceError(
            f"Invio email fallito: refresh token Google non valido o revocato ({risposta.text})"
        )

    access_token = risposta.json().get("access_token")
    if not access_token:
        raise EmailServiceError("Invio email fallito: risposta di Google priva di access_token.")
    return access_token


def invia_email(
    destinatario: str,
    oggetto: str,
    contenuto_html: str,
    contenuto_testo: str | None = None,
) -> None:
    """Invia una email tramite la Gmail API (HTTPS, OAuth2), autenticata come
    l'account Gmail configurato — non SMTP, quindi funziona anche su hosting
    gratuiti che bloccano le porte SMTP in uscita.

    Richiede le variabili d'ambiente:
    - GMAIL_CLIENT_ID / GMAIL_CLIENT_SECRET: credenziali OAuth create su Google
      Cloud Console (tipo "Desktop app").
    - GMAIL_REFRESH_TOKEN: ottenuto una tantum con scripts/gmail_oauth_setup.py.
    - GMAIL_SENDER_EMAIL: indirizzo Gmail mittente (l'account autenticato),
      es. "CUN Fest <iscrizionicunfest@gmail.com>".

    Se contenuto_testo non è fornito, viene derivato automaticamente da contenuto_html.
    """
    sender_email = os.getenv("GMAIL_SENDER_EMAIL")
    if not sender_email:
        raise EmailServiceError("GMAIL_SENDER_EMAIL deve essere configurata come variabile d'ambiente.")

    access_token = _ottieni_access_token()

    messaggio = MIMEMultipart("alternative")
    messaggio["Subject"] = oggetto
    messaggio["From"] = sender_email
    messaggio["To"] = destinatario
    messaggio.attach(MIMEText(contenuto_testo or _html_a_testo(contenuto_html), "plain", "utf-8"))
    messaggio.attach(MIMEText(contenuto_html, "html", "utf-8"))

    raw = base64.urlsafe_b64encode(messaggio.as_bytes()).decode("ascii")

    try:
        risposta = httpx.post(
            GMAIL_SEND_URL,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            json={"raw": raw},
            timeout=10.0,
        )
    except httpx.HTTPError as exc:
        logger.error("Errore di rete nell'invio email a %s tramite Gmail API: %s", destinatario, exc)
        raise EmailServiceError(f"Invio email fallito: errore di rete verso Gmail API ({exc})") from exc

    if risposta.status_code >= 400:
        dettaglio = risposta.text
        logger.error(
            "Gmail API ha rifiutato l'invio a %s (status %s): %s", destinatario, risposta.status_code, dettaglio
        )
        raise EmailServiceError(
            f"Invio email fallito: Gmail API ha risposto con errore {risposta.status_code} ({dettaglio})"
        )

    logger.info("Email inviata con successo a %s (oggetto: %s)", destinatario, oggetto)


# --------------------------------------------------------------------------
# Casi d'uso (costruzione + invio)
# --------------------------------------------------------------------------

def invia_conferma_iscrizione(email: str, contesto: dict) -> None:
    """Invia l'email di conferma iscrizione per un singolo partecipante."""
    pacchetto = costruisci_email_conferma(contesto)
    invia_email(email, pacchetto["oggetto"], pacchetto["html"], pacchetto["testo"])


def invia_aggiornamento_prezzo(email: str, contesto: dict) -> None:
    """Invia l'email con il prezzo aggiornato per un singolo partecipante."""
    pacchetto = costruisci_email_aggiornamento(contesto)
    invia_email(email, pacchetto["oggetto"], pacchetto["html"], pacchetto["testo"])


def invia_annullamento(email: str, nome: str) -> None:
    """Invia l'email di conferma annullamento per una singola iscrizione."""
    pacchetto = costruisci_email_annullamento({"nome": nome})
    invia_email(email, pacchetto["oggetto"], pacchetto["html"], pacchetto["testo"])


def invia_annullamento_nucleo(email: str, nomi: Iterable[str]) -> None:
    """Invia un'unica email di recap per l'annullamento di un intero nucleo familiare."""
    pacchetto = costruisci_email_annullamento_nucleo({"nomi": list(nomi)})
    invia_email(email, pacchetto["oggetto"], pacchetto["html"], pacchetto["testo"])


def invia_comunicazione_massa(email: str, nome: str, oggetto: str, testo_libero: str) -> None:
    """Invia un'email di comunicazione di massa personalizzata nel saluto."""
    pacchetto = costruisci_email_massa(nome, oggetto, testo_libero)
    invia_email(email, pacchetto["oggetto"], pacchetto["html"], pacchetto["testo"])
