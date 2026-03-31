import os
from .base import BaseLLMService
from .claude import ClaudeService
from .openai import OpenAIService

# 注册表：新增 LLM 只需在这里加一行
LLM_REGISTRY = {
    "claude": ClaudeService,
    "openai": OpenAIService,
    # "local":  LocalLLMService,  ← 以后加
}

def get_llm_service() -> BaseLLMService:
    """
    根据环境变量 LLM_PROVIDER 返回对应的 LLM Service。
    默认使用 claude。

    在 .env 里配置：
        LLM_PROVIDER=claude   ← 用 Claude
        LLM_PROVIDER=openai   ← 用 OpenAI
    """
    provider = os.environ.get("LLM_PROVIDER", "claude").lower()

    service_class = LLM_REGISTRY.get(provider)
    if service_class is None:
        supported = list(LLM_REGISTRY.keys())
        raise ValueError(f"不支持的 LLM provider: '{provider}'，目前支持: {supported}")

    service = service_class()

    if not service.is_available():
        raise RuntimeError(f"{provider} 的 API key 未配置，请检查环境变量")

    return service