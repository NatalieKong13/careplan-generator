from django.utils import timezone
from .models import Provider, Patient, Order
from .exceptions import BlockError, WarningException
import datetime


def get_or_create_provider(name: str, npi: str) -> Provider:
    try:
        existing = Provider.objects.get(npi=npi)
    except Provider.DoesNotExist:
        return Provider.objects.create(name=name, npi=npi)

    if existing.name != name:
        raise BlockError(
            message=f"NPI {npi} is already registered under a different name.",
            code="npi_name_conflict",
            detail={"existing_name": existing.name, "provided_name": name},
        )
    return existing


def get_or_create_patient(
    first_name: str,
    last_name: str,
    mrn: str,
    dob,
) -> tuple[Patient, list[str]]:
    """
    Returns (patient, warnings).
    Warnings are non-blocking; caller decides what to do with them.
    Raises on hard conflicts.
    """
    warnings = []

    mrn_match = Patient.objects.filter(mrn=mrn).first()
    name_dob_matches = Patient.objects.filter(
        first_name=first_name,
        last_name=last_name,
        dob=dob,
    ).exclude(mrn=mrn)

    if mrn_match:
        name_matches = (
            mrn_match.first_name == first_name
            and mrn_match.last_name == last_name
        )
        dob_matches = mrn_match.dob == dob

        if name_matches and dob_matches:
            # Perfect match → reuse silently
            return mrn_match, warnings

        # MRN matches but something else differs → warn
        mismatches = []
        if not name_matches:
            mismatches.append(
                f"name (on file: '{mrn_match.first_name} {mrn_match.last_name}', "
                f"provided: '{first_name} {last_name}')"
            )
        if not dob_matches:
            mismatches.append(
                f"date of birth (on file: {mrn_match.dob}, "
                f"provided: {dob})"
            )

        warnings.append(
            f"MRN {mrn} already exists but has mismatched "
            f"{' and '.join(mismatches)}. Using existing record."
        )
        return mrn_match, warnings

    # No MRN match
    if name_dob_matches.exists():
        match = name_dob_matches.first()
        warnings.append(
            f"A patient named '{first_name} {last_name}' with DOB {dob} "
            f"already exists under a different MRN: {match.mrn}. "
            f"Creating new record with MRN {mrn}."
        )

    patient = Patient.objects.create(
        first_name=first_name,
        last_name=last_name,
        mrn=mrn,
        dob=dob,
    )
    return patient, warnings


def create_order(
    patient: Patient,
    medication_name: str,
    provider: Provider,
    diagnosis: str,
    confirm: bool = False,
) -> tuple[Order, list[str]]:
    """
    Creates an Order.
    - Same patient + same medication + same calendar day → hard block (409).
    - Same patient + same medication + different day → warn, but allow if confirm=True.
    Returns (order, warnings).
    """
    warnings = []
    today = datetime.datetime.now(datetime.timezone.utc).date()
    start = datetime.datetime.combine(today, datetime.time.min, tzinfo=datetime.timezone.utc)
    end = datetime.datetime.combine(today, datetime.time.max, tzinfo=datetime.timezone.utc)

    # Hard block: exact duplicate today
    same_day_duplicate = Order.objects.filter(
        patient=patient,
        medication_name=medication_name,
        created_at__gte=start,
        created_at__lte=end,
    ).first()

    if same_day_duplicate:
        raise BlockError(
            message=f"Duplicate order for '{medication_name}' today.",
            code="duplicate_order_same_day",
            detail={"patient_mrn": patient.mrn, "date": str(today)},
        )

    # Soft block: same medication on a prior day
    prior_order = Order.objects.filter(
        patient=patient,
        medication_name=medication_name,
    ).order_by("-created_at").first()

    if prior_order:
        prior_date = prior_order.created_at.date()
        warning_msg = (
            f"Patient {patient.mrn} already has an order for '{medication_name}' "
            f"from {prior_date}. Pass confirm=True to proceed."
        )
        if not confirm:
            raise WarningException(
            message=f"Prior order for '{medication_name}' exists on {prior_date}.",
            code="duplicate_order_prior_day",
            detail={"prior_date": str(prior_date), "confirm_to_proceed": True},
        )

        warnings.append(
            f"Patient {patient.mrn} already has an order for '{medication_name}' "
            f"from {prior_date}. Order created with explicit confirmation."
        )

    order = Order.objects.create(
        patient=patient,
        provider=provider,
        medication_name=medication_name,
        diagnosis=diagnosis,
    )
    return order, warnings