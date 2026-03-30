from dataclasses import dataclass, field
from datetime import date
from typing import Optional

@dataclass
class PatientInfo:
    mrn: str
    first_name:str
    last_name:str
    dob: date
    gender: Optional[str] = None
    weight_kg: Optional[float] = None 

@dataclass
class ProviderInfo:
    name: str
    npi: str
    facility: Optional[str] = None

@dataclass
class MedicationInfo:
    name:str
    ndc: Optional[str] = None
    dosage: Optional[str] = None
    frequency: Optional[str] = None

@dataclass
class InternalOrder:
    patient:PatientInfo
    provider: ProviderInfo
    medication: MedicationInfo
    diagnoses: list[str]
    allergies: list[str] = field(default_factory = list)
    clinical_notes: Optional[str] = None
    confirm: bool = False
    source: Optional[str] = None