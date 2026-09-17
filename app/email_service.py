import logging
import os
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Iterable

logger = logging.getLogger(__name__)

SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "465"))


class EmailServiceError(Exception):
    """Errore applicativo nell'invio di una email tramite SMTP."""


def invia_email(destinatario: str, oggetto: str, contenuto_html: str) -> None:
    """Invia una email tramite il servizio SMTP di Google (Gmail/Workspace).

    Richiede le variabili d'ambiente:
    - SMTP_USER: indirizzo Gmail mittente, usato anche per l'autenticazione.
    - SMTP_PASSWORD: password per le app di Google (non la password normale
      dell'account: va generata da https://myaccount.google.com/apppasswords,
      richiede la verifica in due passaggi attiva sull'account).
    Facoltative:
    - SMTP_SENDER_EMAIL: indirizzo mostrato come mittente, se diverso da SMTP_USER.
    - SMTP_HOST / SMTP_PORT: default smtp.gmail.com:465 (SSL).
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
    messaggio.attach(MIMEText(contenuto_html, "html", "utf-8"))

    try:
        contesto = ssl.create_default_context()
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=contesto, timeout=10.0) as server:
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


def costruisci_email_conferma(
    referente_nome: str,
    referente_cognome: str,
    partecipanti_list: Iterable[dict],
) -> str:
    """Costruisce l'HTML dell'email di conferma iscrizione con il riepilogo dei partecipanti."""
    righe_partecipanti = "".join(
        f"<tr>"
        f"<td>{p.get('nome', '')}</td>"
        f"<td>{p.get('cognome', '')}</td>"
        f"<td>{p.get('data_arrivo', '')}</td>"
        f"<td>{p.get('data_partenza', '')}</td>"
        f"</tr>"
        for p in partecipanti_list
    )

    return f"""
    <html>
      <body>
        <p>Grazie {referente_nome} {referente_cognome}, la tua iscrizione è stata registrata.</p>
        <p>Riepilogo partecipanti:</p>
        <table border="1" cellpadding="5" cellspacing="0">
          <thead>
            <tr>
              <th>Nome</th>
              <th>Cognome</th>
              <th>Data arrivo</th>
              <th>Data partenza</th>
            </tr>
          </thead>
          <tbody>
            {righe_partecipanti}
          </tbody>
        </table>
      </body>
    </html>
    """


def costruisci_email_aggiornamento(
    partecipante_nome: str,
    prezzo_netto: float,
    dettaglio: dict,
) -> str:
    """Costruisce l'HTML dell'email con il prezzo aggiornato e il relativo dettaglio."""
    return f"""
    <html>
      <body>
        <p>Ciao {partecipante_nome},</p>
        <p>Il prezzo calcolato per la tua iscrizione è di <strong>{prezzo_netto:.2f} €</strong>.</p>
        <p>Dettaglio:</p>
        <ul>
          <li>Notti: {dettaglio.get('notti', '-')}</li>
          <li>Pasti: {dettaglio.get('pasti', '-')}</li>
          <li>Fascia: {dettaglio.get('fascia', '-')}</li>
          <li>Sconto: {dettaglio.get('sconto', '-')}</li>
        </ul>
      </body>
    </html>
    """


def costruisci_email_annullamento(dati: dict) -> str:
    """Costruisce l'HTML dell'email di comunicazione di annullamento iscrizione."""
    nome = dati.get("nome", "")
    return f"""
    <html>
      <body>
        <p>Ciao {nome},</p>
        <p>Ti informiamo che la tua iscrizione al CUN FEST è stata <strong>annullata</strong>.</p>
        <p>Per qualsiasi chiarimento contatta la segreteria organizzativa.</p>
      </body>
    </html>
    """


def costruisci_email_massa(nome: str, oggetto: str, testo_libero: str) -> str:
    """Costruisce l'HTML di una comunicazione di massa a partire da un testo libero.

    I paragrafi del testo libero sono separati da righe vuote e vengono
    trasformati in tag <p> distinti.
    """
    paragrafi = [p.strip() for p in testo_libero.split("\n\n") if p.strip()]
    corpo_html = "".join(
        f"<p>{paragrafo.replace(chr(10), '<br>')}</p>" for paragrafo in paragrafi
    )

    return f"""
    <html>
      <body>
        <p>Ciao {nome},</p>
        {corpo_html}
      </body>
    </html>
    """


def invia_conferma_iscrizione(
    referente_nome: str,
    referente_cognome: str,
    email: str,
    partecipanti_list: Iterable[dict],
) -> None:
    """Invia l'email di conferma iscrizione al referente con il riepilogo dei partecipanti."""
    contenuto_html = costruisci_email_conferma(referente_nome, referente_cognome, partecipanti_list)

    invia_email(
        destinatario=email,
        oggetto="Conferma iscrizione CUN FEST",
        contenuto_html=contenuto_html,
    )


def invia_aggiornamento_prezzo(
    email: str,
    partecipante_nome: str,
    prezzo_netto: float,
    dettaglio: dict,
) -> None:
    """Invia l'email con il prezzo calcolato e il relativo dettaglio per un partecipante."""
    contenuto_html = costruisci_email_aggiornamento(partecipante_nome, prezzo_netto, dettaglio)

    invia_email(
        destinatario=email,
        oggetto="Comunicazione prezzo iscrizione CUN FEST",
        contenuto_html=contenuto_html,
    )


# Alias mantenuto per compatibilità con codice esistente.
invia_comunicazione_prezzo = invia_aggiornamento_prezzo
