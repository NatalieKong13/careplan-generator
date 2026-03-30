"""
Patient 重复检测测试套件
运行方式：docker exec -it careplan-celery-backend-1 pytest careplan/tests/ -v --cov=careplan.duplicate_detection
"""
import datetime
import pytest
from unittest.mock import patch, MagicMock
from django.test import TestCase, Client
from django.utils import timezone

from careplan.models import Patient, Provider, Order, CarePlan
from careplan.duplicate_detection import (
    get_or_create_provider,
    get_or_create_patient,
    create_order,
)
from careplan.exceptions import BlockError, WarningException


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures / Helpers
# ─────────────────────────────────────────────────────────────────────────────

def make_patient(**kwargs):
    defaults = dict(
        first_name="John",
        last_name="Doe",
        mrn="MRN001",
        dob=datetime.date(1990, 1, 1),
    )
    defaults.update(kwargs)
    return Patient.objects.create(**defaults)


def make_provider(**kwargs):
    defaults = dict(name="Dr. Smith", npi="1234567890")
    defaults.update(kwargs)
    return Provider.objects.create(**defaults)


def make_order(patient, provider, **kwargs):
    defaults = dict(
        medication_name="Aspirin",
        diagnosis="Headache",
    )
    defaults.update(kwargs)
    return Order.objects.create(patient=patient, provider=provider, **defaults)


# ═════════════════════════════════════════════════════════════════════════════
# UNIT TESTS — get_or_create_provider
# ═════════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestGetOrCreateProvider:

    def test_creates_new_provider_when_npi_not_exists(self):
        provider = get_or_create_provider(name="Dr. Smith", npi="1111111111")
        assert Provider.objects.filter(npi="1111111111").exists()
        assert provider.name == "Dr. Smith"

    def test_returns_existing_provider_when_npi_and_name_match(self):
        existing = make_provider(name="Dr. Smith", npi="2222222222")
        result = get_or_create_provider(name="Dr. Smith", npi="2222222222")
        assert result.id == existing.id
        assert Provider.objects.filter(npi="2222222222").count() == 1

    def test_raises_block_error_when_npi_exists_with_different_name(self):
        make_provider(name="Dr. Smith", npi="3333333333")
        with pytest.raises(BlockError) as exc_info:
            get_or_create_provider(name="Dr. Jones", npi="3333333333")
        assert exc_info.value.code == "npi_name_conflict"
        assert exc_info.value.http_status == 409

    def test_block_error_detail_contains_both_names(self):
        make_provider(name="Dr. Smith", npi="4444444444")
        with pytest.raises(BlockError) as exc_info:
            get_or_create_provider(name="Dr. Jones", npi="4444444444")
        detail = exc_info.value.detail
        assert detail["existing_name"] == "Dr. Smith"
        assert detail["provided_name"] == "Dr. Jones"

    def test_does_not_create_duplicate_provider(self):
        make_provider(name="Dr. Smith", npi="5555555555")
        get_or_create_provider(name="Dr. Smith", npi="5555555555")
        assert Provider.objects.filter(npi="5555555555").count() == 1


# ═════════════════════════════════════════════════════════════════════════════
# UNIT TESTS — get_or_create_patient
# ═════════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestGetOrCreatePatient:

    # ── Perfect match ─────────────────────────────────────────────────────────

    def test_creates_new_patient_when_mrn_not_exists(self):
        patient, warnings = get_or_create_patient(
            first_name="John", last_name="Doe",
            mrn="NEW001", dob=datetime.date(1990, 1, 1),
        )
        assert Patient.objects.filter(mrn="NEW001").exists()
        assert warnings == []

    def test_returns_existing_patient_when_all_fields_match(self):
        existing = make_patient(mrn="MATCH001")
        patient, warnings = get_or_create_patient(
            first_name="John", last_name="Doe",
            mrn="MATCH001", dob=datetime.date(1990, 1, 1),
        )
        assert patient.id == existing.id
        assert warnings == []
        assert Patient.objects.filter(mrn="MATCH001").count() == 1

    # ── MRN match, name mismatch ───────────────────────────────────────────────

    def test_returns_warning_when_mrn_matches_but_first_name_differs(self):
        make_patient(first_name="John", last_name="Doe", mrn="WARN001")
        patient, warnings = get_or_create_patient(
            first_name="Jane", last_name="Doe",
            mrn="WARN001", dob=datetime.date(1990, 1, 1),
        )
        assert len(warnings) == 1
        assert "name" in warnings[0]

    def test_returns_warning_when_mrn_matches_but_last_name_differs(self):
        make_patient(first_name="John", last_name="Doe", mrn="WARN002")
        patient, warnings = get_or_create_patient(
            first_name="John", last_name="Smith",
            mrn="WARN002", dob=datetime.date(1990, 1, 1),
        )
        assert len(warnings) == 1
        assert "name" in warnings[0]

    def test_returns_warning_when_mrn_matches_but_dob_differs(self):
        make_patient(mrn="WARN003", dob=datetime.date(1990, 1, 1))
        patient, warnings = get_or_create_patient(
            first_name="John", last_name="Doe",
            mrn="WARN003", dob=datetime.date(1995, 5, 5),
        )
        assert len(warnings) == 1
        assert "date of birth" in warnings[0]

    def test_returns_warning_when_mrn_matches_but_both_name_and_dob_differ(self):
        make_patient(first_name="John", last_name="Doe",
                     mrn="WARN004", dob=datetime.date(1990, 1, 1))
        patient, warnings = get_or_create_patient(
            first_name="Jane", last_name="Smith",
            mrn="WARN004", dob=datetime.date(1995, 5, 5),
        )
        assert len(warnings) == 1
        assert "name" in warnings[0]
        assert "date of birth" in warnings[0]

    def test_reuses_existing_patient_even_when_name_differs(self):
        existing = make_patient(first_name="John", mrn="WARN005")
        patient, warnings = get_or_create_patient(
            first_name="Jane", last_name="Doe",
            mrn="WARN005", dob=datetime.date(1990, 1, 1),
        )
        assert patient.id == existing.id
        assert Patient.objects.filter(mrn="WARN005").count() == 1

    # ── Name + DOB match, different MRN ───────────────────────────────────────

    def test_returns_warning_when_name_and_dob_match_but_mrn_differs(self):
        make_patient(first_name="John", last_name="Doe",
                     mrn="OLD001", dob=datetime.date(1990, 1, 1))
        patient, warnings = get_or_create_patient(
            first_name="John", last_name="Doe",
            mrn="NEW999", dob=datetime.date(1990, 1, 1),
        )
        assert len(warnings) == 1
        assert "OLD001" in warnings[0]

    def test_creates_new_patient_when_name_and_dob_match_but_mrn_differs(self):
        make_patient(first_name="John", last_name="Doe",
                     mrn="OLD002", dob=datetime.date(1990, 1, 1))
        patient, warnings = get_or_create_patient(
            first_name="John", last_name="Doe",
            mrn="NEW998", dob=datetime.date(1990, 1, 1),
        )
        assert Patient.objects.filter(mrn="NEW998").exists()

    # ── No match at all ────────────────────────────────────────────────────────

    def test_creates_patient_with_no_warnings_when_truly_new(self):
        patient, warnings = get_or_create_patient(
            first_name="Alice", last_name="Wonder",
            mrn="BRAND001", dob=datetime.date(2000, 6, 15),
        )
        assert patient.first_name == "Alice"
        assert warnings == []

    def test_saved_patient_has_correct_fields(self):
        get_or_create_patient(
            first_name="Bob", last_name="Builder",
            mrn="FIELDS001", dob=datetime.date(1985, 3, 22),
        )
        p = Patient.objects.get(mrn="FIELDS001")
        assert p.first_name == "Bob"
        assert p.last_name == "Builder"
        assert p.dob == datetime.date(1985, 3, 22)


# ═════════════════════════════════════════════════════════════════════════════
# UNIT TESTS — create_order
# ═════════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestCreateOrder:

    def setup_method(self):
        self.patient = make_patient(mrn="ORD_PATIENT")
        self.provider = make_provider(npi="9999999999")

    def test_creates_order_successfully_when_no_prior_orders(self):
        order, warnings = create_order(
            patient=self.patient,
            provider=self.provider,
            medication_name="Aspirin",
            diagnosis="Headache",
        )
        assert Order.objects.filter(id=order.id).exists()
        assert warnings == []

    def test_raises_block_error_on_same_day_duplicate(self):
        # Create first order directly in DB with today's UTC timestamp
        today_utc = datetime.datetime.now(datetime.timezone.utc)
        order = Order.objects.create(
            patient=self.patient,
            provider=self.provider,
            medication_name="Aspirin",
            diagnosis="Headache",
        )
        # Patch created_at to today
        Order.objects.filter(id=order.id).update(created_at=today_utc)

        with pytest.raises(BlockError) as exc_info:
            create_order(
                patient=self.patient,
                provider=self.provider,
                medication_name="Aspirin",
                diagnosis="Headache",
            )
        assert exc_info.value.code == "duplicate_order_same_day"
        assert exc_info.value.http_status == 409

    def test_raises_warning_exception_on_prior_day_duplicate_without_confirm(self):
        yesterday = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=1)
        order = Order.objects.create(
            patient=self.patient,
            provider=self.provider,
            medication_name="Aspirin",
            diagnosis="Headache",
        )
        Order.objects.filter(id=order.id).update(created_at=yesterday)

        with pytest.raises(WarningException) as exc_info:
            create_order(
                patient=self.patient,
                provider=self.provider,
                medication_name="Aspirin",
                diagnosis="Headache",
                confirm=False,
            )
        assert exc_info.value.code == "duplicate_order_prior_day"
        assert exc_info.value.http_status == 200

    def test_creates_order_with_warning_when_prior_day_and_confirm_true(self):
        yesterday = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=1)
        order = Order.objects.create(
            patient=self.patient,
            provider=self.provider,
            medication_name="Aspirin",
            diagnosis="Headache",
        )
        Order.objects.filter(id=order.id).update(created_at=yesterday)

        new_order, warnings = create_order(
            patient=self.patient,
            provider=self.provider,
            medication_name="Aspirin",
            diagnosis="Headache",
            confirm=True,
        )
        assert Order.objects.filter(id=new_order.id).exists()
        assert len(warnings) == 1

    def test_different_medication_does_not_trigger_duplicate(self):
        today_utc = datetime.datetime.now(datetime.timezone.utc)
        order = Order.objects.create(
            patient=self.patient,
            provider=self.provider,
            medication_name="Aspirin",
            diagnosis="Headache",
        )
        Order.objects.filter(id=order.id).update(created_at=today_utc)

        # Different medication → should succeed
        new_order, warnings = create_order(
            patient=self.patient,
            provider=self.provider,
            medication_name="Ibuprofen",
            diagnosis="Back pain",
        )
        assert Order.objects.filter(id=new_order.id).exists()

    def test_different_patient_does_not_trigger_duplicate(self):
        today_utc = datetime.datetime.now(datetime.timezone.utc)
        other_patient = make_patient(mrn="OTHER_PATIENT")
        order = Order.objects.create(
            patient=other_patient,
            provider=self.provider,
            medication_name="Aspirin",
            diagnosis="Headache",
        )
        Order.objects.filter(id=order.id).update(created_at=today_utc)

        # Different patient → should succeed
        new_order, warnings = create_order(
            patient=self.patient,
            provider=self.provider,
            medication_name="Aspirin",
            diagnosis="Headache",
        )
        assert Order.objects.filter(id=new_order.id).exists()


# ═════════════════════════════════════════════════════════════════════════════
# INTEGRATION TESTS — POST /api/careplan/
# ═════════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestCreateCareplanEndpoint:

    def setup_method(self):
        self.client = Client()
        self.url = "/api/careplan/"
        self.base_payload = {
            "patient": {
                "mrn": "INT001",
                "first_name": "Integration",
                "last_name": "Test",
                "dob": "1990-01-01",
            },
            "provider": {
                "npi": "0000000001",
                "name": "Dr. Integration",
            },
            "medication_name": "TestMed",
            "diagnosis": "Test diagnosis",
        }

    def _post(self, payload=None):
        import json
        data = payload or self.base_payload
        return self.client.post(
            self.url,
            data=json.dumps(data),
            content_type="application/json",
        )

    # ── Provider conflicts ─────────────────────────────────────────────────────

    @patch("careplan.services.generate_careplan_task")
    def test_npi_name_conflict_returns_409(self, mock_task):
        mock_task.delay = MagicMock()
        make_provider(name="Dr. Real", npi="0000000001")

        payload = dict(self.base_payload)
        payload["provider"] = {"npi": "0000000001", "name": "Dr. Fake"}
        response = self._post(payload)

        assert response.status_code == 409
        body = response.json()
        assert body["success"] is False
        assert body["type"] == "block_error"
        assert body["code"] == "npi_name_conflict"

    # ── Order duplicates ───────────────────────────────────────────────────────

    @patch("careplan.services.generate_careplan_task")
    def test_same_day_order_returns_409(self, mock_task):
        mock_task.delay = MagicMock()

        # First request succeeds
        self._post()

        # Second request same day → 409
        response = self._post()
        assert response.status_code == 409
        body = response.json()
        assert body["code"] == "duplicate_order_same_day"

    @patch("careplan.services.generate_careplan_task")
    def test_prior_day_order_without_confirm_returns_200_with_warning(self, mock_task):
        mock_task.delay = MagicMock()

        # Create a prior order manually
        patient = make_patient(mrn="INT001", first_name="Integration",
                               last_name="Test", dob=datetime.date(1990, 1, 1))
        provider = make_provider(npi="0000000001", name="Dr. Integration")
        yesterday = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=1)
        order = Order.objects.create(
            patient=patient, provider=provider,
            medication_name="TestMed", diagnosis="Test diagnosis",
        )
        Order.objects.filter(id=order.id).update(created_at=yesterday)

        response = self._post()
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert "warnings" in body
        assert body["warnings"][0]["code"] == "duplicate_order_prior_day"

    @patch("careplan.services.generate_careplan_task")
    def test_prior_day_order_with_confirm_true_succeeds(self, mock_task):
        mock_task.delay = MagicMock()

        patient = make_patient(mrn="INT001", first_name="Integration",
                               last_name="Test", dob=datetime.date(1990, 1, 1))
        provider = make_provider(npi="0000000001", name="Dr. Integration")
        yesterday = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=1)
        order = Order.objects.create(
            patient=patient, provider=provider,
            medication_name="TestMed", diagnosis="Test diagnosis",
        )
        Order.objects.filter(id=order.id).update(created_at=yesterday)

        payload = dict(self.base_payload)
        payload["confirm"] = True
        response = self._post(payload)

        assert response.status_code == 200

    # ── Patient warnings ───────────────────────────────────────────────────────

    @patch("careplan.services.generate_careplan_task")
    def test_mrn_match_with_different_name_still_creates_careplan(self, mock_task):
        mock_task.delay = MagicMock()
        make_patient(first_name="WRONG", last_name="NAME",
                     mrn="INT001", dob=datetime.date(1990, 1, 1))

        response = self._post()
        # Should succeed (warning only, not a block)
        assert response.status_code in [200, 201]

    # ── Missing fields ─────────────────────────────────────────────────────────

    def test_missing_patient_field_returns_error(self):
        import json
        payload = {"provider": {"npi": "0000000001", "name": "Dr. Test"},
                   "medication_name": "X", "diagnosis": "Y"}
        response = self.client.post(
            self.url, data=json.dumps(payload),
            content_type="application/json",
        )
        assert response.status_code in [400, 500]

    def test_malformed_json_returns_error(self):
        response = self.client.post(
            self.url, data="not json",
            content_type="application/json",
        )
        assert response.status_code in [400, 500]


# ═════════════════════════════════════════════════════════════════════════════
# ERROR FORMAT TESTS — ensure all errors follow unified schema
# ═════════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestErrorResponseFormat:

    def setup_method(self):
        self.client = Client()
        self.url = "/api/careplan/"

    @patch("careplan.services.generate_careplan_task")
    def test_block_error_has_required_fields(self, mock_task):
        mock_task.delay = MagicMock()
        make_provider(name="Dr. Real", npi="ERR0000001")

        import json
        payload = {
            "patient": {"mrn": "ERR001", "first_name": "A",
                        "last_name": "B", "dob": "1990-01-01"},
            "provider": {"npi": "ERR0000001", "name": "Dr. Fake"},
            "medication_name": "X", "diagnosis": "Y",
        }
        response = self.client.post(
            self.url, data=json.dumps(payload),
            content_type="application/json",
        )
        body = response.json()
        assert "success" in body
        assert "type" in body
        assert "code" in body
        assert "message" in body
        assert body["success"] is False

    def test_404_returns_error_for_nonexistent_careplan(self):
        response = self.client.get("/api/careplan/99999/")
        assert response.status_code == 404