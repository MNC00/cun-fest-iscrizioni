import unittest
from unittest.mock import patch

from app import main
from app.models import ImpostazioneApp, LogEvento


class FakeSettingsSession:
    def __init__(self):
        self.settings = {}
        self.events = []
        self.committed = False

    def get(self, model, key):
        if model is ImpostazioneApp:
            return self.settings.get(key)
        return None

    def add(self, entity):
        if isinstance(entity, ImpostazioneApp):
            self.settings[entity.chiave] = entity
        elif isinstance(entity, LogEvento):
            self.events.append(entity)

    def commit(self):
        self.committed = True


class DriveConfigurationTests(unittest.TestCase):
    def test_admin_can_save_a_drive_folder_url(self):
        db = FakeSettingsSession()
        with patch.object(main, "_richiedi_operatore_admin", return_value=("admin", None)):
            response = main.configurazione_salva_cartella_drive(
                request=object(),
                url_o_id="https://drive.google.com/drive/folders/folder_123?usp=sharing",
                db=db,
            )

        self.assertEqual(response.status_code, 303)
        self.assertEqual(db.settings[main.CHIAVE_CARTELLA_DRIVE].valore, "folder_123")
        self.assertTrue(db.committed)
        self.assertEqual(db.events[0].azione, "cartella_drive_ricevute_modificata")

    def test_invalid_folder_url_is_not_saved(self):
        db = FakeSettingsSession()
        with patch.object(main, "_richiedi_operatore_admin", return_value=("admin", None)):
            response = main.configurazione_salva_cartella_drive(
                request=object(), url_o_id="https://example.com/not-a-drive-folder", db=db
            )

        self.assertEqual(response.status_code, 303)
        self.assertFalse(db.settings)
        self.assertFalse(db.committed)

    def test_saved_folder_overrides_environment_fallback(self):
        db = FakeSettingsSession()
        db.settings[main.CHIAVE_CARTELLA_DRIVE] = ImpostazioneApp(
            chiave=main.CHIAVE_CARTELLA_DRIVE, valore="database-folder"
        )
        with patch.dict("os.environ", {"GOOGLE_DRIVE_FOLDER_ID": "environment-folder"}):
            self.assertEqual(main._cartella_drive_configurata(db), "database-folder")

    def test_environment_folder_is_used_until_admin_selects_one(self):
        db = FakeSettingsSession()
        with patch.dict("os.environ", {"GOOGLE_DRIVE_FOLDER_ID": "environment-folder"}):
            self.assertEqual(main._cartella_drive_configurata(db), "environment-folder")


if __name__ == "__main__":
    unittest.main()