from datetime import date
from typing import List, Optional

from pydantic import BaseModel, EmailStr, field_validator, model_validator

TIPI_EVENTO_VALIDI = {"precun_cun", "campo_famiglie_cun", "solo_cun"}


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
    flag_bosco_domenica: bool = False
    flag_cena_ristorante_domenica: Optional[bool] = None
    tipo_evento: str = "solo_cun"
    note: Optional[str] = None
    fascia_prezzo: str = "Generale"

    @field_validator("tipo_evento")
    @classmethod
    def valida_tipo_evento(cls, valore: str) -> str:
        if valore not in TIPI_EVENTO_VALIDI:
            raise ValueError(f"tipo_evento non valido: deve essere uno tra {sorted(TIPI_EVENTO_VALIDI)}.")
        return valore


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
