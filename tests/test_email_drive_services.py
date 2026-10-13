import json
import os
import unittest
from unittest.mock import Mock, patch

from app.drive_service import DriveServiceError, carica_ricevuta_drive
from app.email_service import costruisci_email_conferma_nucleo, invia_conferma_nucleo


def contesto(nome: str, prezzo: float | None) -> dict:
    return {
        "nome": nome,
        "anno": 2026,
        "hasPrezzo": prezzo is not None,
        "isSoloPranzo": False,
        "dataArrivoFormattata": "sabato 1 agosto 2026",
        "pastoArrivo": "Cena",
        "dataPartenzaFormattata": "domenica 2 agosto 2026",
        "pastoPartenza": "Pranzo",
        "prezzo": prezzo,
        "linkAnnullamento": None,
        "linkRicevute": None,
    }


class EmailConfirmationTests(unittest.TestCase):
    def test_family_confirmation_contains_every_participant_and_price(self):
        messaggio = costruisci_email_conferma_nucleo(
            [contesto("Anna", 120), contesto("Luca", 85)]
        )

        self.assertEqual(messaggio["html"].count("<h3>"), 2)
        self.assertIn("€120.00", messaggio["html"])
        self.assertIn("€85.00", messaggio["html"])
        self.assertIn("Anna", messaggio["testo"])
        self.assertIn("Luca", messaggio["testo"])

    def test_unavailable_price_has_actionable_guidance(self):
        messaggio = costruisci_email_conferma_nucleo([contesto("Anna", None)])

        self.assertIn("Verifica date ed eventi selezionati", messaggio["html"])
        self.assertNotIn("comunicati i prezzi", messaggio["html"])

    @patch("app.email_service.invia_email")
    def test_family_confirmation_sends_one_message(self, invia_email):
        invia_conferma_nucleo("famiglia@example.org", [contesto("Anna", 120), contesto("Luca", 85)])

        invia_email.assert_called_once()
        self.assertEqual(invia_email.call_args.args[0], "famiglia@example.org")


class DriveServiceTests(unittest.TestCase):
    def test_upload_targets_configured_folder_and_returns_file_id(self):
        risposta = Mock(status_code=200)
        risposta.json.return_value = {"id": "drive-file-123"}
        with (
            patch.dict(os.environ, {"GOOGLE_DRIVE_FOLDER_ID": "folder-123"}),
            patch("app.drive_service._access_token", return_value="access-token"),
            patch("app.drive_service.httpx.post", return_value=risposta) as post,
        ):
            file_id = carica_ricevuta_drive("ricevuta.pdf", b"pdf-bytes", "application/pdf")

        self.assertEqual(file_id, "drive-file-123")
        metadata = json.loads(post.call_args.kwargs["files"]["metadata"][1])
        self.assertEqual(metadata["parents"], ["folder-123"])
        self.assertEqual(post.call_args.kwargs["files"]["file"][1], b"pdf-bytes")

    def test_upload_requires_folder_configuration(self):
        with patch.dict(os.environ, {}, clear=True), patch("app.drive_service._access_token") as token:
            with self.assertRaises(DriveServiceError):
                carica_ricevuta_drive("ricevuta.pdf", b"pdf-bytes", "application/pdf")

        token.assert_not_called()


if __name__ == "__main__":
    unittest.main()