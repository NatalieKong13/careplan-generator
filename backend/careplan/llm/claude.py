import os
import anthropic
from .base import BaseLLMService

class ClaudeService(BaseLLMService):
    def __init__(self):
        self.api_key = os.environ.get("ANTHROPIC_API_KEY")
        self.model = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-20250514")
        self.client = anthropic.Anthropic(api_key = self.api_key)

    def generate(self, prompt: str) -> str:
        message = self.client.messages.create(
            model=self.model,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}]
        )
        return message.content[0].text

    def is_available(self) -> bool:
        return bool(self.api_key)