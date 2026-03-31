from abc import ABC, abstractmethod

class BaseLLMService(ABC):

    @abstractmethod
    def generate(self, prompt: str) -> str:
        ...

    @abstractmethod
    def is_available(self) -> bool:
        ...
