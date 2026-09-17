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
    flag_parliamo_solo_lunedi: bool = False
    note: Optional[str] = None
    fascia_prezzo: str = "Generale"


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
