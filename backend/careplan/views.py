import json
import io
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.conf import settings
from django.db.models import Q
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.units import inch
from .models import Patient, Provider, Order, CarePlan
from .tasks import generate_careplan_task  # 导入 Celery 任务


@csrf_exempt
@require_http_methods(["POST"])
def create_order_and_generate_careplan(request):
    """
    异步模式（Celery 版本）：
    1. 存数据库 (status='pending')
    2. 触发 Celery 异步任务
    3. 立刻返回
    """
    data = json.loads(request.body)
    
    # 1. 创建或获取 Patient
    patient, _ = Patient.objects.get_or_create(
        mrn=data['patient']['mrn'],
        defaults={
            'first_name': data['patient']['first_name'],
            'last_name': data['patient']['last_name'],
            'dob': data['patient']['dob'],
        }
    )
    
    # 2. 创建或获取 Provider
    provider, _ = Provider.objects.get_or_create(
        npi=data['provider']['npi'],
        defaults={'name': data['provider']['name']}
    )
    
    # 3. 创建 Order
    order = Order.objects.create(
        patient=patient,
        provider=provider,
        medication_name=data['medication_name'],
        diagnosis=data['diagnosis'],
    )
    
    # 4. 创建 CarePlan (pending 状态)
    careplan = CarePlan.objects.create(order=order, status='pending')
    
    # 5. 触发 Celery 异步任务
    generate_careplan_task.delay(careplan.id)
    print(f"[API] Celery task triggered for CarePlan {careplan.id}")
    
    # 6. 立刻返回
    return JsonResponse({
        'message': 'Request received, processing in background',
        'order_id': order.id,
        'careplan_id': careplan.id,
        'status': 'pending',
    })


@require_http_methods(["GET"])
def get_careplan(request, careplan_id):
    """获取单个care plan"""
    try:
        careplan = CarePlan.objects.select_related('order__patient', 'order__provider').get(id=careplan_id)
        return JsonResponse({
            'id': careplan.id,
            'status': careplan.status,
            'patient': {
                'mrn': careplan.order.patient.mrn,
                'name': f"{careplan.order.patient.first_name} {careplan.order.patient.last_name}",
                'dob': str(careplan.order.patient.dob),
            },
            'provider': {
                'npi': careplan.order.provider.npi,
                'name': careplan.order.provider.name,
            },
            'medication': careplan.order.medication_name,
            'diagnosis': careplan.order.diagnosis,
            'careplan': {
                'problem_list': careplan.problem_list,
                'goals': careplan.goals,
                'pharmacist_interventions': careplan.pharmacist_interventions,
                'monitoring_plan': careplan.monitoring_plan,
            },
            'created_at': careplan.created_at.isoformat(),
        })
    except CarePlan.DoesNotExist:
        return JsonResponse({'error': 'Not found'}, status=404)


@require_http_methods(["GET"])
def list_careplans(request):
    """列出所有care plans"""
    careplans = CarePlan.objects.select_related('order__patient').order_by('-created_at')[:50]
    return JsonResponse({
        'careplans': [{
            'id': cp.id,
            'status': cp.status,
            'patient_name': f"{cp.order.patient.first_name} {cp.order.patient.last_name}",
            'medication': cp.order.medication_name,
            'created_at': cp.created_at.isoformat(),
        } for cp in careplans]
    })


@require_http_methods(["GET"])
def search_careplans(request):
    """搜索care plans - 按患者名字或药物名搜索"""
    query = request.GET.get('q', '').strip()
    
    if not query:
        return JsonResponse({'careplans': []})
    
    careplans = CarePlan.objects.select_related('order__patient').filter(
        Q(order__patient__first_name__icontains=query) |
        Q(order__patient__last_name__icontains=query) |
        Q(order__medication_name__icontains=query) |
        Q(order__patient__mrn__icontains=query)
    ).order_by('-created_at')[:50]
    
    return JsonResponse({
        'careplans': [{
            'id': cp.id,
            'status': cp.status,
            'patient_name': f"{cp.order.patient.first_name} {cp.order.patient.last_name}",
            'mrn': cp.order.patient.mrn,
            'medication': cp.order.medication_name,
            'created_at': cp.created_at.isoformat(),
        } for cp in careplans]
    })


@require_http_methods(["GET"])
def download_careplan_pdf(request, careplan_id):
    """下载 Care Plan 为 PDF"""
    try:
        careplan = CarePlan.objects.select_related('order__patient', 'order__provider').get(id=careplan_id)
    except CarePlan.DoesNotExist:
        return JsonResponse({'error': 'Not found'}, status=404)
    
    # 创建 PDF
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, topMargin=0.5*inch, bottomMargin=0.5*inch)
    styles = getSampleStyleSheet()
    
    # 自定义样式
    title_style = ParagraphStyle('Title', parent=styles['Heading1'], fontSize=18, spaceAfter=20)
    section_style = ParagraphStyle('Section', parent=styles['Heading2'], fontSize=14, spaceAfter=10, spaceBefore=15)
    body_style = ParagraphStyle('Body', parent=styles['Normal'], fontSize=11, spaceAfter=10)
    
    story = []
    
    # 标题
    story.append(Paragraph("CVS Care Plan", title_style))
    story.append(Spacer(1, 0.2*inch))
    
    # 患者信息
    patient = careplan.order.patient
    provider = careplan.order.provider
    story.append(Paragraph(f"<b>Patient:</b> {patient.first_name} {patient.last_name}", body_style))
    story.append(Paragraph(f"<b>MRN:</b> {patient.mrn}", body_style))
    story.append(Paragraph(f"<b>DOB:</b> {patient.dob}", body_style))
    story.append(Paragraph(f"<b>Provider:</b> {provider.name} (NPI: {provider.npi})", body_style))
    story.append(Paragraph(f"<b>Medication:</b> {careplan.order.medication_name}", body_style))
    story.append(Paragraph(f"<b>Diagnosis:</b> {careplan.order.diagnosis}", body_style))
    story.append(Spacer(1, 0.3*inch))
    
    # Care Plan 内容
    story.append(Paragraph("Problem List", section_style))
    story.append(Paragraph(careplan.problem_list, body_style))
    
    story.append(Paragraph("Goals", section_style))
    story.append(Paragraph(careplan.goals, body_style))
    
    story.append(Paragraph("Pharmacist Interventions", section_style))
    story.append(Paragraph(careplan.pharmacist_interventions, body_style))
    
    story.append(Paragraph("Monitoring Plan", section_style))
    story.append(Paragraph(careplan.monitoring_plan, body_style))
    
    # 生成 PDF
    doc.build(story)
    buffer.seek(0)
    
    # 返回 PDF
    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="careplan_{careplan_id}.pdf"'
    return response


@require_http_methods(["GET"])
def get_careplan_status(request, careplan_id):
    try:
        careplan = CarePlan.objects.get(id=careplan_id)
    except CarePlan.DoesNotExist:
        return JsonResponse({'error': 'Not found'}, status=404)

    response_data = {
        'id':careplan.id,
        'status' : careplan.status,
    }

    if careplan.status == 'completed':
        response_data['content'] = {
            'problem_list': careplan.problem_list,
            'goals': careplan.goals,
            'pharmacist_interventions': careplan.pharmacist_interventions,
            'monitoring_plan': careplan.monitoring_plan,
        }
    
    if careplan.status == 'failed':
        response_data['error_message'] = careplan.error_message
    
    return JsonResponse(response_data)
    
