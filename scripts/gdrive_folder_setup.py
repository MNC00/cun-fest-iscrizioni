"""Crea una cartella Drive per le ricevute usando l'OAuth Google configurato."""
from app.drive_service import DriveServiceError, crea_cartella_ricevute


def main() -> None:
    try:
        folder_id = crea_cartella_ricevute()
    except DriveServiceError as exc:
        raise SystemExit(str(exc)) from exc

    print("Cartella creata. Configura questa variabile d'ambiente:")
    print(f"GOOGLE_DRIVE_FOLDER_ID={folder_id}")
    print("Condividi poi la cartella con gli operatori esterni desiderati da Google Drive.")


if __name__ == "__main__":
    main()