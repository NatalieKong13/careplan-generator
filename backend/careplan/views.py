import json
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from . import services, serializers
from .exceptions import NotFoundError


@csrf_exempt
@require_http_methods(["POST"])
def create_order_and_generate_careplan(request):
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"success": False, "type": "validation_error",
                             "code": "invalid_json", "message": "Invalid JSON."}, status=400)
    try:
        order, careplan = services.create_careplan(data)
    except KeyError as e:
        return JsonResponse({"success": False, "type": "validation_error",
                             "code": "missing_field", "message": f"Missing field: {e}"}, status=400)
    return JsonResponse(serializers.serialize_careplan_created(order, careplan))


@require_http_methods(["GET"])
def get_careplan(request, careplan_id):
    careplan = services.get_careplan(careplan_id)
    if careplan is None:
        raise NotFoundError(f"Careplan {careplan_id} not found.")
    return JsonResponse(serializers.serialize_careplan_detail(careplan))


@require_http_methods(["GET"])
def get_careplan_status(request, careplan_id):
    careplan = services.get_careplan_status(careplan_id)
    if careplan is None:
        return JsonResponse({'error': 'Not found'}, status=404)
    return JsonResponse(serializers.serialize_careplan_status(careplan))


@require_http_methods(["GET"])
def list_careplans(request):
    careplans = services.list_careplans()
    return JsonResponse(serializers.serialize_careplan_list(careplans))


@require_http_methods(["GET"])
def search_careplans(request):
    query = request.GET.get('q', '').strip()
    careplans = services.search_careplans(query)
    return JsonResponse(serializers.serialize_careplan_search(careplans))


@require_http_methods(["GET"])
def download_careplan_pdf(request, careplan_id):
    careplan = services.get_careplan(careplan_id)
    if careplan is None:
        return JsonResponse({'error': 'Not found'}, status=404)
    buffer = services.generate_careplan_pdf(careplan)
    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="careplan_{careplan_id}.pdf"'
    return response