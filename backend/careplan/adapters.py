from abc import ABC, abstractmethod
from datetime import datetime
from .schemas import InternalOrder, PatientInfo, ProviderInfo, MedicationInfo
from .base_adapter import BaseIntakeAdapter
import xml.etree.ElementTree as ET
import json


# ── 工具函数 ──────────────────────────────────────────────

def parse_date(date_str: str):
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m/%d/%y"):
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"无法解析日期: {date_str}")

def flatten_diagnoses(dx: dict) -> list[str]:
    result = []
    for value in dx.values():
        if isinstance(value, list):
            result.extend(value)
        else:
            result.append(value)
    return result


# ── ClinicBAdapter：小型诊所 JSON ─────────────────────────

class ClinicBAdapter(BaseIntakeAdapter):
    """
    处理小型诊所发来的 JSON 格式数据。
    raw_data 是已经 json.loads() 过的 dict。
    """

    def parse(self):
        """提取需要的字段，存成统一结构，同时保留原始数据用于排查。"""
        self._parsed = {
            "mrn":          self.raw_data['pt']['mrn'],
            "first_name":   self.raw_data['pt']['fname'],
            "last_name":    self.raw_data['pt']['lname'],
            "dob":          self.raw_data['pt']['dob'],
            "gender":       self.raw_data['pt'].get('gender'),
            "weight_kg":    self.raw_data['pt'].get('wt'),
            "provider_name": self.raw_data['provider']['name'],
            "npi":          self.raw_data['provider']['npi_num'],
            "med_name":     self.raw_data['rx']['med_name'],
            "ndc":          self.raw_data['rx'].get('ndc'),
            "dosage":       self.raw_data['rx'].get('dosage'),
            "frequency":    self.raw_data['rx'].get('freq'),
            "diagnoses":    flatten_diagnoses(self.raw_data['dx']),
            "allergies":    self.raw_data.get('allergies', []),
            "clinical_notes": self.raw_data.get('clinical_notes'),
            "confirm":      self.raw_data.get('confirm', False),
            # 保留原始数据，方便排查问题
            "_raw":         self.raw_data,
        }

    def validate(self) -> None:
        """检查必填字段是否存在且格式正确。"""
        required = ["mrn", "first_name", "last_name", "dob", "provider_name", "npi", "med_name"]
        for field in required:
            if not self._parsed.get(field):
                raise ValueError(f"缺少必填字段: {field}")

        # 验证日期格式能被解析
        parse_date(self._parsed["dob"])

        # 验证 NPI 是纯数字且10位
        npi = self._parsed["npi"]
        if not npi.isdigit() or len(npi) != 10:
            raise ValueError(f"NPI 格式不正确: {npi}，应为10位数字")

    def transform(self) -> InternalOrder:
        """把 _parsed 组装成 InternalOrder。"""
        p = self._parsed
        return InternalOrder(
            source="CLINIC_B",
            patient=PatientInfo(
                mrn=p["mrn"],
                first_name=p["first_name"],
                last_name=p["last_name"],
                dob=parse_date(p["dob"]),
                gender=p["gender"],
                weight_kg=p["weight_kg"],
            ),
            provider=ProviderInfo(
                name=p["provider_name"],
                npi=p["npi"],
            ),
            medication=MedicationInfo(
                name=p["med_name"],
                ndc=p["ndc"],
                dosage=p["dosage"],
                frequency=p["frequency"],
            ),
            diagnoses=p["diagnoses"],
            allergies=p["allergies"],
            clinical_notes=p["clinical_notes"],
            confirm=p["confirm"],
        )


# ── 旧函数保留，内部改用 ClinicBAdapter ───────────────────

def from_clinic_json(data: dict) -> InternalOrder:
    return ClinicBAdapter(data).run()


# ── PharmaCorp XML（暂时保留旧写法）─────────────────────

def from_pharmacorp_xml(xml_body: bytes) -> InternalOrder:
    root = ET.fromstring(xml_body)

    diagnoses = []
    primary = root.find("DiagnosisList/PrimaryDiagnosis/ICDCode")
    if primary is not None:
        diagnoses.append(primary.text)
    for dx in root.findall("DiagnosisList/SecondaryDiagnoses/Diagnosis/ICDCode"):
        diagnoses.append(dx.text)

    return InternalOrder(
        source="PHARMACORP",
        patient=PatientInfo(
            mrn=root.find("PatientInformation/MedicalRecordNumber").text,
            first_name=root.find("PatientInformation/PatientName/FirstName").text,
            last_name=root.find("PatientInformation/PatientName/LastName").text,
            dob=parse_date(root.find("PatientInformation/DateOfBirth").text),
        ),
        provider=ProviderInfo(
            name=root.find("PrescriberInformation/FullName").text,
            npi=root.find("PrescriberInformation/NPINumber").text,
            facility=root.findtext("PrescriberInformation/Facility"),
        ),
        medication=MedicationInfo(
            name=root.find("MedicationOrder/DrugName").text,
            ndc=root.findtext("MedicationOrder/NDCCode"),
            dosage=root.findtext("MedicationOrder/OrderedDose/Amount"),
            frequency=root.findtext("MedicationOrder/Frequency"),
        ),
        diagnoses=diagnoses,
        clinical_notes=root.findtext("ClinicalDocumentation/NarrativeText"),
    )


class MedCenterAdapter(BaseIntakeAdapter):
    """
    处理 MedCenter Hospital 发来的 XML 格式数据。
    raw_data 是 XML bytes。
    """

    def parse(self):
        root = ET.fromstring(self.raw_data)

        # 提取所有诊断 code
        diagnoses = []
        main = root.find("ConditionList/MainCondition")
        if main is not None:
            diagnoses.append(main.get("code"))  # 注意：code 是 XML attribute 不是 text！
        for cond in root.findall("ConditionList/AdditionalConditions/Condition"):
            diagnoses.append(cond.get("code"))

        # 提取过敏信息
        allergies = [
            item.text
            for item in root.findall("PatientAllergies/AllergyItem")
        ]

        self._parsed = {
            "mrn":            root.find("SubjectOfCare/ChartNumber").text,
            "first_name":     root.find("SubjectOfCare/LegalName/Given").text,
            "last_name":      root.find("SubjectOfCare/LegalName/Family").text,
            "dob":            root.find("SubjectOfCare/BirthDate").text,
            "gender":         root.findtext("SubjectOfCare/BiologicalSex"),
            "weight_kg":      root.findtext("SubjectOfCare/MassKg"),
            "provider_name":  root.find("ReferringPhysician/DisplayName").text,
            "npi":            root.find("ReferringPhysician/ProviderID").text,
            "facility":       root.findtext("ReferringPhysician/Department"),
            "med_name":       root.find("TherapyOrder/ProductName").text,
            "ndc":            root.findtext("TherapyOrder/ProductCode"),
            "dosage":         root.findtext("TherapyOrder/DoseAmount"),
            "frequency":      root.findtext("TherapyOrder/Schedule"),
            "diagnoses":      diagnoses,
            "allergies":      allergies,
            "clinical_notes": root.findtext("ClinicalSummary"),
            "_raw":           self.raw_data,  # 保留原始数据
        }

    def validate(self) -> None:
        required = ["mrn", "first_name", "last_name", "dob", "provider_name", "npi", "med_name"]
        for field in required:
            if not self._parsed.get(field):
                raise ValueError(f"缺少必填字段: {field}")

        parse_date(self._parsed["dob"])

        npi = self._parsed["npi"]
        if not npi.isdigit() or len(npi) != 10:
            raise ValueError(f"NPI 格式不正确: {npi}")

    def transform(self) -> InternalOrder:
        p = self._parsed
        return InternalOrder(
            source="MEDCENTER",
            patient=PatientInfo(
                mrn=p["mrn"],
                first_name=p["first_name"],
                last_name=p["last_name"],
                dob=parse_date(p["dob"]),
                gender=p["gender"],
                weight_kg=float(p["weight_kg"]) if p["weight_kg"] else None,
            ),
            provider=ProviderInfo(
                name=p["provider_name"],
                npi=p["npi"],
                facility=p["facility"],
            ),
            medication=MedicationInfo(
                name=p["med_name"],
                ndc=p["ndc"],
                dosage=p["dosage"],
                frequency=p["frequency"],
            ),
            diagnoses=p["diagnoses"],
            allergies=p["allergies"],
            clinical_notes=p["clinical_notes"],
        )
    

ADAPTER_REGISTRY = {
    "CLINIC_B":   ClinicBAdapter,
    "MEDCENTER":  MedCenterAdapter, 
    # "PHARMACORP": PharmaCorpAdapter,   ← 下一步加
    # "CVS":        CVSWebFormAdapter,   ← 下一步加
}

def get_adapter(source: str, raw_data) -> BaseIntakeAdapter:
    """
    根据来源返回对应的 Adapter 实例。

    用法：
        adapter = get_adapter("CLINIC_B", data)
        order = adapter.run()
    """
    adapter_class = ADAPTER_REGISTRY.get(source.upper())
    if adapter_class is None:
        supported = list(ADAPTER_REGISTRY.keys())
        raise ValueError(f"不支持的数据源: '{source}'，目前支持: {supported}")
    return adapter_class(raw_data)