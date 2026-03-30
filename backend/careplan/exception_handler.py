from django.http import JsonResponse
from rest_framework.views import exception_handler as drf_default_handler
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.response import Response

from .exceptions import BaseAppException, ValidationError, WarningException


def app_exception_handler(exc, context):
    """
    统一异常处理器，注册到 settings.EXCEPTION_HANDLER。

    处理顺序：
    1. 我们自己的 BaseAppException（含三个子类）
    2. DRF 原生 ValidationError（serializer 自动抛出的）
    3. 其他所有异常 → 交给 DRF 默认 handler
    """

    if isinstance(exc, BaseAppException):
        body = {"success": False, **exc.to_dict()}

        
        if isinstance(exc, WarningException):
            body = {
                "success": True,
                "warnings": [exc.to_dict()],
            }

        return JsonResponse(body, status=exc.http_status)

    if isinstance(exc, DRFValidationError):
        body = {
            "success": False,
            "type": "validation_error",
            "code": "invalid_input",
            "message": "Request validation failed.",
            "detail": exc.detail,          
        }
        return JsonResponse(body, status=400)

    return drf_default_handler(exc, context)