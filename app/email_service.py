import logging
import os
from typing import Iterable

import httpx

logger = logging.getLogger(__name__)

BREVO_API_URL = "https://api.brevo.com/v3/smtp/email"


class EmailServiceError(Exception):
    """Errore applicativo nell'invio di una email tramite Brevo."""


def invia_email(destinatario: str, oggetto: str, contenuto_html: str) -> None:
    """Invia una email tramite le API transazionali di Brevo."""
    api_key = os.getenv("BREVO_API_KEY")
    sender_email = os.getenv("BREVO_SENDER_EMAIL")

    if not api_key or not sender_email:
        raise EmailServiceError(
            "BREVO_API_KEY e BREVO_SENDER_EMAIL devono essere configurate come variabili d'ambiente."
        )

    payload = {
        "sender": {"email": sender_email},
        "to": [{"email": destinatario}],
        "subject": oggetto,
        "htmlContent": contenuto_html,
    }
    headers = {
        "accept": "application/json",
        "api-key": api_key,
        "content-type": "application/json",
    }

    try:
        response = httpx.post(BREVO_API_URL, json=payload, headers=headers, timeout=10.0)
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        logger.error(
            "Errore Brevo nell'invio email a %s: status=%s body=%s",
            destinatario,
            exc.response.status_code,
            exc.response.text,
        )
        raise EmailServiceError(
            f"Invio email fallito ({exc.response.status_code}): {exc.response.text}"
        ) from exc
    except httpx.RequestError as exc:
        logger.error("Errore di connessione a Brevo nell'invio email a %s: %s", destinatario, exc)
        raise EmailServiceError(f"Invio email fallito: errore di connessione a Brevo ({exc})") from exc

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
