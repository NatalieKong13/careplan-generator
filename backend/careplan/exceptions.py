from dataclasses import dataclass, field
from typing import Any


class BaseAppException(Exception):
    """
    所有业务异常的基类。
    子类只需要设置 default_type / default_code / default_http_status，
    然后 raise 时传 message 和可选的 detail。
    """
    default_type: str = "error"
    default_code: str = "unknown_error"
    default_http_status: int = 500

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        detail: Any = None,
        http_status: int | None = None,
    ):
        super().__init__(message)
        self.type = self.default_type
        self.code = code or self.default_code
        self.message = message
        self.detail = detail                              # 额外上下文，可以是 dict/list/None
        self.http_status = http_status or self.default_http_status

    def to_dict(self) -> dict:
        payload = {
            "type": self.type,
            "code": self.code,
            "message": self.message,
        }
        if self.detail is not None:
            payload["detail"] = self.detail
        return payload


class ValidationError(BaseAppException):
    """
    用户输入格式不对。
    serializer 通过 raise ValidationError(...) 主动抛出，
    或由 exception_handler 捕获 DRF ValidationError 后统一转换。
    """
    default_type = "validation_error"
    default_code = "invalid_input"
    default_http_status = 400


class BlockError(BaseAppException):
    """
    业务规则阻止操作继续。用户无法通过"确认"绕过。
    例：同一 NPI 对应不同 Provider 名字。
    """
    default_type = "block_error"
    default_code = "business_rule_violated"
    default_http_status = 409


class WarningException(BaseAppException):
    """
    操作被允许，但有潜在风险，返回 200 + warnings 字段。
    注意：这不是真正的"错误"，handler 会特殊处理它。
    """
    default_type = "warning"
    default_code = "needs_confirmation"
    default_http_status = 200

class NotFoundError(BaseAppException):
    default_type = "not_found"
    default_code = "resource_not_found"
    default_http_status = 404