def serialize_careplan_created(order, careplan):
    """POST /careplan/ 的返回格式"""
    return {
        'message': 'Request received, processing in background',
        'order_id': order.id,
        'careplan_id': careplan.id,
        'status': 'pending',
    }


def serialize_careplan_detail(careplan):
    """GET /careplan/<id>/ 的返回格式"""
    return {
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
    }


def serialize_careplan_status(careplan):
    """GET /careplan/<id>/status/ 的返回格式"""
    data = {
        'id': careplan.id,
        'status': careplan.status,
    }
    if careplan.status == 'completed':
        data['content'] = {
            'problem_list': careplan.problem_list,
            'goals': careplan.goals,
            'pharmacist_interventions': careplan.pharmacist_interventions,
            'monitoring_plan': careplan.monitoring_plan,
        }
    if careplan.status == 'failed':
        data['error_message'] = careplan.error_message
    return data


def serialize_careplan_list(careplans):
    """GET /careplans/ 的返回格式"""
    return {
        'careplans': [{
            'id': cp.id,
            'status': cp.status,
            'patient_name': f"{cp.order.patient.first_name} {cp.order.patient.last_name}",
            'medication': cp.order.medication_name,
            'created_at': cp.created_at.isoformat(),
        } for cp in careplans]
    }


def serialize_careplan_search(careplans):
    """GET /careplans/search/ 的返回格式"""
    return {
        'careplans': [{
            'id': cp.id,
            'status': cp.status,
            'patient_name': f"{cp.order.patient.first_name} {cp.order.patient.last_name}",
            'mrn': cp.order.patient.mrn,
            'medication': cp.order.medication_name,
            'created_at': cp.created_at.isoformat(),
        } for cp in careplans]
    }