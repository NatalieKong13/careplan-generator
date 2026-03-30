import io
from django.db.models import Q
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.units import inch
from .models import Patient, Provider, Order, CarePlan
from .tasks import generate_careplan_task
from .duplicate_detection import get_or_create_provider, get_or_create_patient, create_order as detect_create_order

def create_careplan(data):
    patient, _ = get_or_create_patient(
        first_name=data['patient']['first_name'],
        last_name=data['patient']['last_name'],
        mrn=data['patient']['mrn'],
        dob=data['patient']['dob'],
    )

    provider = get_or_create_provider(
        name=data['provider']['name'],
        npi=data['provider']['npi'],
    )

    confirm = data.get('confirm', False)
    order, _ = detect_create_order(
        patient=patient,
        provider=provider,
        medication_name=data['medication_name'],
        diagnosis=data['diagnosis'],
        confirm=data.get('confirm', False),
    )

    order.diagnosis = data['diagnosis']
    order.provider = provider
    order.save()

    careplan = CarePlan.objects.create(order=order, status='pending')
    generate_careplan_task.delay(careplan.id)
    print(f"[API] Celery task triggered for CarePlan {careplan.id}")

    return order, careplan


def get_careplan(careplan_id):
    """获取单个 careplan，不存在返回 None"""
    try:
        return CarePlan.objects.select_related(
            'order__patient', 'order__provider'
        ).get(id=careplan_id)
    except CarePlan.DoesNotExist:
        return None


def get_careplan_status(careplan_id):
    """获取 careplan 状态，不存在返回 None"""
    try:
        return CarePlan.objects.get(id=careplan_id)
    except CarePlan.DoesNotExist:
        return None


def list_careplans():
    """返回最近50条 careplan"""
    return CarePlan.objects.select_related('order__patient').order_by('-created_at')[:50]


def search_careplans(query):
    """按患者姓名、MRN、药物名搜索"""
    if not query:
        return CarePlan.objects.none()
    return CarePlan.objects.select_related('order__patient').filter(
        Q(order__patient__first_name__icontains=query) |
        Q(order__patient__last_name__icontains=query) |
        Q(order__medication_name__icontains=query) |
        Q(order__patient__mrn__icontains=query)
    ).order_by('-created_at')[:50]


def generate_careplan_pdf(careplan):
    """生成 PDF，返回 BytesIO buffer"""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, topMargin=0.5*inch, bottomMargin=0.5*inch)
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle('Title', parent=styles['Heading1'], fontSize=18, spaceAfter=20)
    section_style = ParagraphStyle('Section', parent=styles['Heading2'], fontSize=14, spaceAfter=10, spaceBefore=15)
    body_style = ParagraphStyle('Body', parent=styles['Normal'], fontSize=11, spaceAfter=10)

    story = []

    story.append(Paragraph("CVS Care Plan", title_style))
    story.append(Spacer(1, 0.2*inch))

    patient = careplan.order.patient
    provider = careplan.order.provider
    story.append(Paragraph(f"<b>Patient:</b> {patient.first_name} {patient.last_name}", body_style))
    story.append(Paragraph(f"<b>MRN:</b> {patient.mrn}", body_style))
    story.append(Paragraph(f"<b>DOB:</b> {patient.dob}", body_style))
    story.append(Paragraph(f"<b>Provider:</b> {provider.name} (NPI: {provider.npi})", body_style))
    story.append(Paragraph(f"<b>Medication:</b> {careplan.order.medication_name}", body_style))
    story.append(Paragraph(f"<b>Diagnosis:</b> {careplan.order.diagnosis}", body_style))
    story.append(Spacer(1, 0.3*inch))

    story.append(Paragraph("Problem List", section_style))
    story.append(Paragraph(careplan.problem_list, body_style))

    story.append(Paragraph("Goals", section_style))
    story.append(Paragraph(careplan.goals, body_style))

    story.append(Paragraph("Pharmacist Interventions", section_style))
    story.append(Paragraph(careplan.pharmacist_interventions, body_style))

    story.append(Paragraph("Monitoring Plan", section_style))
    story.append(Paragraph(careplan.monitoring_plan, body_style))

    doc.build(story)
    buffer.seek(0)
    return buffer