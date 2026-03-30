# middleware.py
import json
from django.http import JsonResponse
from .exceptions import BaseAppException, WarningException


class AppExceptionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_exception(self, request, exc):
        if isinstance(exc, BaseAppException):
            if isinstance(exc, WarningException):
                body = {
                    "success": True,
                    "warnings": [exc.to_dict()],
                }
            else:
                body = {"success": False, **exc.to_dict()}
            return JsonResponse(body, status=exc.http_status)

        # 不认识的异常 → 返回 None，Django 继续用默认处理
        return None