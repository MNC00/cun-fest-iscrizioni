"""Crea o aggiorna un account operatore.

Uso interattivo:
    python scripts/crea_operatore.py

Uso non interattivo (utile in automazioni/CI):
    python scripts/crea_operatore.py --username mario --password "segreta123" --nome "Mario Rossi"

Per rendere un operatore amministratore (accesso alla sezione /configurazione:
date evento, tariffe, gestione altri operatori):
    python scripts/crea_operatore.py --username mario --password "segreta123" --admin

Se lo username esiste già, l'operatore viene aggiornato (password, nome,
stato attivo, ruolo amministratore) invece di crearne uno duplicato.
ATTENZIONE: --disattiva e --admin vanno ripassati ad ogni esecuzione dello
script sullo stesso operatore, altrimenti vengono azzerati (es. resettare la
password di un amministratore senza ripassare --admin lo declassa a
operatore normale).
"""

import argparse
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.auth import hash_password  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.models import Operatore  # noqa: E402


def crea_o_aggiorna_operatore(
    username: str, password: str, nome: str | None, attivo: bool, is_admin: bool
) -> str:
    db = SessionLocal()
    try:
        operatore = db.query(Operatore).filter(Operatore.username == username).first()
        password_hash = hash_password(password)

        if operatore:
            operatore.password_hash = password_hash
            operatore.nome = nome or operatore.nome
            operatore.attivo = attivo
            operatore.is_admin = is_admin
            esito = "aggiornato"
        else:
            operatore = Operatore(
                username=username,
                password_hash=password_hash,
                nome=nome,
                attivo=attivo,
                is_admin=is_admin,
            )
            db.add(operatore)
            esito = "creato"

        db.commit()
        return esito
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description="Crea o aggiorna un operatore CUN Fest.")
    parser.add_argument("--username", help="Username univoco dell'operatore")
    parser.add_argument("--password", help="Password in chiaro (se omessa, viene richiesta)")
    parser.add_argument("--nome", help="Nome e cognome dell'operatore (opzionale)")
    parser.add_argument(
        "--disattiva",
        action="store_true",
        help="Crea/aggiorna l'operatore come NON attivo (non potrà effettuare il login)",
    )
    parser.add_argument(
        "--admin",
        action="store_true",
        help=(
            "Rende l'operatore amministratore (accesso alla sezione /configurazione: "
            "date evento, tariffe, gestione operatori). Come per --disattiva, va "
            "ripassato ad ogni esecuzione: se omesso, il ruolo amministratore viene rimosso."
        ),
    )
    args = parser.parse_args()

    username = args.username or input("Username operatore: ").strip()
    if not username:
        print("Username obbligatorio.", file=sys.stderr)
        sys.exit(1)

    password = args.password or getpass.getpass("Password: ")
    if not password:
        print("Password obbligatoria.", file=sys.stderr)
        sys.exit(1)

    nome = args.nome
    if nome is None and args.username is None:
        # Modalità interattiva: chiedi anche il nome (facoltativo)
        nome = input("Nome e cognome (opzionale): ").strip() or None

    esito = crea_o_aggiorna_operatore(
        username, password, nome, attivo=not args.disattiva, is_admin=args.admin
    )
    print(f"Operatore '{username}' {esito} con successo.")


if __name__ == "__main__":
    main()
