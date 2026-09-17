from datetime import date
from typing import List, Optional

from pydantic import BaseModel, EmailStr, model_validator


class ReferenteRequest(BaseModel):
    nome: str
    cognome: str
    email: EmailStr
    telefono: Optional[str] = None
    zona_provenienza: Optional[str] = None


class PartecipanteRequest(BaseModel):
    nome: str
    cognome: str
    data_nascita: Optional[date] = None
    luogo_nascita: Optional[str] = None
    zona_provenienza: Optional[str] = None
    data_arrivo: Optional[date] = None
    data_partenza: Optional[date] = None
    pasto_arrivo: Optional[str] = None
    pasto_partenza: Optional[str] = None
    flag_solo_pranzo_cun: bool = False
    flag_precun: bool = False
    flag_campo_famiglie: bool = False
    flag_cun_fest: bool = False
    flag_bosco_domenica: bool = False
    flag_cena_ristorante_domenica: Optional[bool] = None
    note: Optional[str] = None
    fascia_prezzo: str = "Altro"

    @model_validator(mode="after")
    def valida_combinazione_eventi(self) -> "PartecipanteRequest":
        if self.flag_solo_pranzo_cun:
            if self.flag_precun or self.flag_campo_famiglie or self.flag_cun_fest:
                raise ValueError(
                    "'Solo pranzo CUN' è un'iscrizione a sé: non selezionare anche PreCunFest, "
                    "Campo Famiglie o CunFest."
                )
            return self

        if not self.data_arrivo or not self.data_partenza:
            raise ValueError("Data di arrivo e di partenza sono obbligatorie.")

        if self.flag_precun and self.flag_campo_famiglie:
            raise ValueError(
                "PreCunFest e Campo Famiglie si svolgono in contemporanea: selezionane solo uno."
            )
        if not (self.flag_precun or self.flag_campo_famiglie or self.flag_cun_fest):
            raise ValueError(
                "Seleziona almeno un evento (PreCunFest, Campo Famiglie o CunFest) oppure 'Solo pranzo CUN'."
            )
        return self


class IscrizioneFamigliaRequest(BaseModel):
    referente: Optional[ReferenteRequest] = None
    famiglia_esistente_email: Optional[EmailStr] = None
    partecipanti: List[PartecipanteRequest]

    @model_validator(mode="after")
    def valida_referente_o_famiglia_esistente(self) -> "IscrizioneFamigliaRequest":
        if not self.referente and not self.famiglia_esistente_email:
            raise ValueError(
                "Specificare i dati del referente oppure l'email di un nucleo familiare già iscritto."
            )
        if self.referente and self.famiglia_esistente_email:
            raise ValueError(
                "Specificare solo uno tra i dati del referente e l'email del nucleo familiare esistente."
            )
        return self
