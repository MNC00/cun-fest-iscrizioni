import unittest
from datetime import date
from unittest.mock import patch

from app import main
from app.calcolo import CalcoloPrezzoError
from app.models import Famiglia, Partecipante
from app.schemas import IscrizioneFamigliaRequest


class FakeSession:
    def __init__(self):
        self.entities = []
        self.next_family_id = 1
        self.next_participant_id = 1
        self.commit_count = 0

    def add(self, entity):
        if isinstance(entity, Famiglia) and entity.id is None:
            entity.id = self.next_family_id
            self.next_family_id += 1
        elif isinstance(entity, Partecipante) and entity.id is None:
            entity.id = self.next_participant_id
            self.next_participant_id += 1
        self.entities.append(entity)

    def flush(self):
        pass

    def commit(self):
        self.commit_count += 1

    def rollback(self):
        pass


def payload_famiglia() -> IscrizioneFamigliaRequest:
    partecipanti = [
        {
            "nome": nome,
            "cognome": "Rossi",
            "data_arrivo": date(2026, 8, 1),
            "data_partenza": date(2026, 8, 2),
            "flag_cun_fest": True,
        }
        for nome in ("Anna", "Luca")
    ]
    return IscrizioneFamigliaRequest(
        referente={"nome": "Anna", "cognome": "Rossi", "email": "famiglia@example.org"},
        partecipanti=partecipanti,
    )


class SignupFlowTests(unittest.TestCase):
    def test_signup_calculates_prices_syncs_payments_and_sends_one_family_email(self):
        db = FakeSession()
        with (
            patch.object(main, "ottieni_periodo_evento", return_value=(None, None)),
            patch.object(main, "calcola_prezzo_partecipante") as calcola,
            patch.object(main, "sincronizza_pagamento") as sincronizza,
            patch.object(
                main,
                "_contesto_email_partecipante",
                side_effect=lambda p, _db: {"nome": p.nome, "hasPrezzo": p.prezzo_netto is not None},
            ),
            patch.object(main, "invia_conferma_nucleo") as invia,
        ):
            def calcola_prezzo(partecipante, _db):
                partecipante.prezzo_netto = 100
                return {"prezzo_netto": 100}

            calcola.side_effect = calcola_prezzo
            risposta = main.iscriviti(payload_famiglia(), db)

        self.assertEqual(risposta["status"], "ok")
        self.assertEqual(calcola.call_count, 2)
        self.assertEqual(sincronizza.call_count, 4)
        invia.assert_called_once()
        self.assertEqual(invia.call_args.kwargs["email"], "famiglia@example.org")
        self.assertEqual([c["nome"] for c in invia.call_args.kwargs["contesti"]], ["Anna", "Luca"])
        self.assertTrue(all(c["hasPrezzo"] for c in invia.call_args.kwargs["contesti"]))

    def test_missing_tariff_does_not_abort_other_family_members(self):
        db = FakeSession()
        with (
            patch.object(main, "ottieni_periodo_evento", return_value=(None, None)),
            patch.object(main, "calcola_prezzo_partecipante") as calcola,
            patch.object(main, "sincronizza_pagamento"),
            patch.object(
                main,
                "_contesto_email_partecipante",
                side_effect=lambda p, _db: {"nome": p.nome, "hasPrezzo": p.prezzo_netto is not None},
            ),
            patch.object(main, "invia_conferma_nucleo") as invia,
        ):
            def calcola_prezzo(partecipante, _db):
                if partecipante.nome == "Anna":
                    raise CalcoloPrezzoError("Tariffa non trovata")
                partecipante.prezzo_netto = 100
                return {"prezzo_netto": 100}

            calcola.side_effect = calcola_prezzo
            main.iscriviti(payload_famiglia(), db)

        invia.assert_called_once()
        contesti = invia.call_args.kwargs["contesti"]
        self.assertEqual([c["hasPrezzo"] for c in contesti], [False, True])

    @patch.object(main, "invia_annullamento_nucleo")
    def test_operator_can_cancel_remaining_family_from_cancelled_head(self, invia):
        db = FakeSession()
        famiglia = Famiglia(
            referente_nome="Anna", referente_cognome="Rossi", email="famiglia@example.org"
        )
        referente = Partecipante(nome="Anna", cognome="Rossi", stato_iscrizione="Annullata")
        altro = Partecipante(nome="Luca", cognome="Rossi", stato_iscrizione="Inviata")
        referente.famiglia = famiglia
        altro.famiglia = famiglia
        famiglia.partecipanti = [referente, altro]

        ok, errore = main._esegui_annullamento(
            db, referente, famiglia, "nucleo", operatore_label="operatore"
        )

        self.assertTrue(ok)
        self.assertIsNone(errore)
        self.assertEqual(altro.stato_iscrizione, "Annullata")
        invia.assert_called_once_with(email="famiglia@example.org", nomi=["Luca Rossi"])


if __name__ == "__main__":
    unittest.main()