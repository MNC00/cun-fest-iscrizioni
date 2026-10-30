import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

from app import calcolo, main
from app.models import (
    STATI_ISCRIZIONE,
    STATO_ATTIVA,
    STATO_DA_CALCOLARE,
    Partecipante,
)


def sql_destinatari(**kwargs) -> str:
    """Solo la clausola WHERE: l'elenco colonne del SELECT contiene sempre tutti i campi."""
    query = main._query_destinatari(Session(), **kwargs)
    sql = str(query.statement.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
    return sql.partition("WHERE")[2]


class StatiIscrizioneTests(unittest.TestCase):
    def test_only_three_states_are_allowed(self):
        self.assertEqual(set(STATI_ISCRIZIONE), {"Attiva", "Annullata", "Da_calcolare"})

    def test_new_enrollment_starts_as_da_calcolare(self):
        colonna = Partecipante.__table__.c.stato_iscrizione
        self.assertEqual(colonna.default.arg, STATO_DA_CALCOLARE)
        self.assertFalse(colonna.nullable)

    def test_database_rejects_any_other_state(self):
        vincoli = [c.sqltext.text for c in Partecipante.__table__.constraints if c.name == "ck_partecipanti_stato_iscrizione"]
        self.assertEqual(len(vincoli), 1)
        for stato in STATI_ISCRIZIONE:
            self.assertIn(f"'{stato}'", vincoli[0])
        for vecchio in ("Inviata", "Calcolata", "Confermata"):
            self.assertNotIn(vecchio, vincoli[0])

    def test_successful_calculation_makes_enrollment_attiva(self):
        partecipante = Partecipante(id=1, nome="Anna", cognome="Rossi", stato_iscrizione=STATO_DA_CALCOLARE)
        dettagli = {"notti": 1, "prezzo_lordo": 50, "sconto_eta": 0, "prezzo_netto": 50}

        calcolo._salva_e_logga(partecipante, Mock(), dettagli)

        self.assertEqual(partecipante.stato_iscrizione, STATO_ATTIVA)


class DestinatariComunicazioniTests(unittest.TestCase):
    def test_filters_by_provenance_not_by_price_band(self):
        sql = sql_destinatari(provenienza="Centro")

        self.assertIn("partecipanti.zona_provenienza = 'Centro'", sql)
        self.assertNotIn("fascia_prezzo", sql)

    def test_filters_by_each_of_the_three_states(self):
        for stato in STATI_ISCRIZIONE:
            self.assertIn(f"partecipanti.stato_iscrizione = '{stato}'", sql_destinatari(stato_iscrizione=stato))

    def test_multiple_events_match_at_least_one_by_default(self):
        sql = sql_destinatari(eventi=["precun", "cun_fest"])

        self.assertIn("flag_precun IS true OR partecipanti.flag_cun_fest IS true", sql)

    def test_multiple_events_can_require_all(self):
        sql = sql_destinatari(eventi=["precun", "cun_fest"], tutti_gli_eventi=True)

        self.assertIn("flag_precun IS true AND partecipanti.flag_cun_fest IS true", sql)

    def test_no_event_selected_means_no_event_filter(self):
        self.assertNotIn("flag_", sql_destinatari(eventi=[]))

    def test_unknown_events_are_ignored(self):
        sql = sql_destinatari(eventi=["inesistente", "precun"])

        self.assertIn("flag_precun IS true", sql)
        self.assertNotIn("inesistente", sql)

    def test_filters_combine(self):
        sql = sql_destinatari(provenienza="Nord", stato_iscrizione="Attiva", eventi=["campo_famiglie"])

        for frammento in ("zona_provenienza = 'Nord'", "stato_iscrizione = 'Attiva'", "flag_campo_famiglie IS true"):
            self.assertIn(frammento, sql)


class ComunicazioniTemplateTests(unittest.TestCase):
    def render(self, filtri: dict) -> str:
        request = SimpleNamespace(
            url=SimpleNamespace(path="/comunicazioni"),
            url_for=lambda name, **kwargs: "/static/css/style.css",
            query_params={},
        )
        template = main.templates.env.get_template("comunicazioni.html")
        with patch.dict(main.templates.env.globals, {"is_admin_operatore": lambda r: False}):
            return template.render(
                request=request,
                title="Comunicazioni",
                username="op",
                filtri=filtri,
                numero_destinatari=0,
                oggetto="",
                testo_libero="",
                risultato=None,
            )

    def test_offers_provenances_and_exactly_the_three_states(self):
        html = self.render(main._filtri_comunicazioni_default())

        for provenienza in ("Nord", "Centro", "Sud"):
            self.assertIn(f'value="{provenienza}"', html)
        for etichetta in ("Attiva", "Annullata", "Da calcolare"):
            self.assertIn(f">{etichetta}</option>", html)
        for rimosso in ("Inviata", "Calcolata", "Confermata", "Fascia"):
            self.assertNotIn(rimosso, html)

    def test_events_are_checkboxes_and_selection_is_preserved(self):
        filtri = {**main._filtri_comunicazioni_default(), "tipo_evento": ["precun", "cun_fest"]}
        html = self.render(filtri)

        self.assertEqual(html.count('type="checkbox" name="tipo_evento"'), len(main.TIPI_EVENTO_LABELS))
        self.assertRegex(html, r'id="evento-precun" value="precun"\s+checked')
        self.assertRegex(html, r'id="evento-cun_fest" value="cun_fest"\s+checked')
        self.assertNotRegex(html, r'id="evento-campo_famiglie" value="campo_famiglie"\s+checked')

    def test_combination_mode_is_preserved(self):
        html = self.render({**main._filtri_comunicazioni_default(), "combinazione_eventi": "tutti"})

        self.assertRegex(html, r'id="combinazione-tutti" value="tutti"\s+checked')
        self.assertNotRegex(html, r'id="combinazione-qualsiasi" value="qualsiasi"\s+checked')


if __name__ == "__main__":
    unittest.main()
