"""Costruzione e invio delle email del CUN Fest.

I contenuti (testo, struttura, formulazioni) replicano fedelmente quelli del
vecchio sistema (Google Apps Script, Domain/Email.js): stesso IBAN, stesso
paragrafo pagamento, stesse varianti "solo pranzo CUN" / prezzo noto o meno.
L'invio vero e proprio avviene via SMTP Google (Gmail), non più tramite Brevo.
"""
import logging
import os
import re
import smtplib
import ssl
from datetime import date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Iterable

logger = logging.getLogger(__name__)

SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "465"))

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
# Invio SMTP
# --------------------------------------------------------------------------

def invia_email(
    destinatario: str,
    oggetto: str,
    contenuto_html: str,
    contenuto_testo: str | None = None,
) -> None:
    """Invia una email tramite il servizio SMTP di Google (Gmail/Workspace).

    Richiede le variabili d'ambiente:
    - SMTP_USER: indirizzo Gmail mittente, usato anche per l'autenticazione.
    - SMTP_PASSWORD: password per le app di Google (non la password normale
      dell'account: va generata da https://myaccount.google.com/apppasswords,
      richiede la verifica in due passaggi attiva sull'account).
    Facoltative:
    - SMTP_SENDER_EMAIL: indirizzo mostrato come mittente, se diverso da SMTP_USER.
    - SMTP_HOST / SMTP_PORT: default smtp.gmail.com:465 (SSL).

    Se contenuto_testo non è fornito, viene derivato automaticamente da contenuto_html.
    """
    smtp_user = os.getenv("SMTP_USER")
    smtp_password = os.getenv("SMTP_PASSWORD")
    sender_email = os.getenv("SMTP_SENDER_EMAIL") or smtp_user

    if not smtp_user or not smtp_password:
        raise EmailServiceError(
            "SMTP_USER e SMTP_PASSWORD devono essere configurate come variabili d'ambiente."
        )

    messaggio = MIMEMultipart("alternative")
    messaggio["Subject"] = oggetto
    messaggio["From"] = sender_email
    messaggio["To"] = destinatario
    messaggio.attach(MIMEText(contenuto_testo or _html_a_testo(contenuto_html), "plain", "utf-8"))
    messaggio.attach(MIMEText(contenuto_html, "html", "utf-8"))

    try:
        contesto_ssl = ssl.create_default_context()
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=contesto_ssl, timeout=10.0) as server:
            server.login(smtp_user, smtp_password)
            server.sendmail(sender_email, [destinatario], messaggio.as_string())
    except smtplib.SMTPAuthenticationError as exc:
        logger.error("Errore di autenticazione SMTP nell'invio email a %s: %s", destinatario, exc)
        raise EmailServiceError(
            "Invio email fallito: credenziali SMTP non valide (verifica SMTP_USER/SMTP_PASSWORD "
            "e che sia stata usata una password per le app di Google)."
        ) from exc
    except (smtplib.SMTPException, OSError) as exc:
        logger.error("Errore SMTP nell'invio email a %s: %s", destinatario, exc)
        raise EmailServiceError(f"Invio email fallito: errore SMTP ({exc})") from exc

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
