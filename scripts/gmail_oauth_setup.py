"""Script da eseguire UNA TANTUM (in locale) per ottenere il refresh token
Google necessario a inviare email tramite la Gmail API (vedi app/email_service.py).

Prerequisiti (da fare una sola volta su https://console.cloud.google.com):
1. Crea un progetto (o riusane uno esistente).
2. Abilita la "Gmail API" (menu API e servizi > Libreria).
3. Configura la schermata di consenso OAuth (tipo "Esterno" va bene, anche in
   modalità "Testing": basta aggiungere l'indirizzo Gmail mittente come
   "utente di test").
4. Crea credenziali OAuth 2.0 di tipo "App desktop" (API e servizi >
   Credenziali > Crea credenziali > ID client OAuth). Annota Client ID e
   Client secret.

Uso:
    python scripts/gmail_oauth_setup.py

Lo script apre il browser, chiede di autenticarti con l'account Gmail che
invierà le email (es. iscrizionicunfest@gmail.com) e stampa il refresh token
da salvare come variabile d'ambiente GMAIL_REFRESH_TOKEN (in .env e su Render).
"""
import http.server
import threading
import urllib.parse
import webbrowser

import httpx

REDIRECT_PORT = 8765
REDIRECT_URI = f"http://localhost:{REDIRECT_PORT}/"
SCOPE = "https://www.googleapis.com/auth/gmail.send"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"

_codice_ricevuto: dict[str, str] = {}


class _CallbackHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 (nome richiesto da BaseHTTPRequestHandler)
        query = urllib.parse.urlparse(self.path).query
        parametri = urllib.parse.parse_qs(query)
        codice = parametri.get("code", [None])[0]

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()

        if codice:
            _codice_ricevuto["code"] = codice
            self.wfile.write(
                "<html><body><h2>Autorizzazione completata.</h2>"
                "<p>Puoi chiudere questa finestra e tornare al terminale.</p></body></html>".encode("utf-8")
            )
        else:
            self.wfile.write(
                "<html><body><h2>Autorizzazione non riuscita.</h2></body></html>".encode("utf-8")
            )

    def log_message(self, format, *args):  # noqa: A002 - silenzia i log del server
        pass


def main() -> None:
    client_id = input("Client ID OAuth (da Google Cloud Console): ").strip()
    client_secret = input("Client secret OAuth: ").strip()

    parametri_auth = {
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": SCOPE,
        "access_type": "offline",
        "prompt": "consent",
    }
    url_autorizzazione = f"{AUTH_URL}?{urllib.parse.urlencode(parametri_auth)}"

    server = http.server.HTTPServer(("localhost", REDIRECT_PORT), _CallbackHandler)
    thread = threading.Thread(target=server.handle_request, daemon=True)
    thread.start()

    print("\nApro il browser per l'autorizzazione Google.")
    print("Accedi con l'account Gmail che invierà le email (es. iscrizionicunfest@gmail.com).\n")
    print(f"Se il browser non si apre da solo, visita questo link:\n{url_autorizzazione}\n")
    webbrowser.open(url_autorizzazione)

    thread.join(timeout=180)

    codice = _codice_ricevuto.get("code")
    if not codice:
        print("Nessun codice di autorizzazione ricevuto entro 3 minuti. Riprova.")
        return

    risposta = httpx.post(
        TOKEN_URL,
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "code": codice,
            "grant_type": "authorization_code",
            "redirect_uri": REDIRECT_URI,
        },
        timeout=10.0,
    )

    if risposta.status_code >= 400:
        print(f"Errore nello scambio del codice: {risposta.status_code} - {risposta.text}")
        return

    dati = risposta.json()
    refresh_token = dati.get("refresh_token")

    if not refresh_token:
        print(
            "Nessun refresh_token restituito da Google. Se hai già autorizzato in passato "
            "questa app, revoca l'accesso da https://myaccount.google.com/permissions e riprova "
            "(Google invia il refresh token solo alla prima autorizzazione, o forzando il "
            "riconsenso, già gestito da questo script con 'prompt=consent')."
        )
        return

    print("\nFatto! Aggiungi queste variabili d'ambiente (.env locale e Render):\n")
    print(f"GMAIL_CLIENT_ID={client_id}")
    print(f"GMAIL_CLIENT_SECRET={client_secret}")
    print(f"GMAIL_REFRESH_TOKEN={refresh_token}")
    print("GMAIL_SENDER_EMAIL=CUN Fest <indirizzo-usato-per-autorizzare@gmail.com>")


if __name__ == "__main__":
    main()
