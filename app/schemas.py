from datetime import date
from typing import List, Optional

from pydantic import BaseModel, EmailStr


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
    zona_provenienza: Optional[str] = None
    data_arrivo: Optional[date] = None
    data_partenza: Optional[date] = None
    pasto_arrivo: Optional[str] = None
    pasto_partenza: Optional[str] = None
    flag_solo_pranzo_cun: bool = False
    flag_parliamo_solo_lunedi: bool = False
    fascia_prezzo: str = "Generale"


class IscrizioneFamigliaRequest(BaseModel):
    referente: ReferenteRequest
    partecipanti: List[PartecipanteRequest]
