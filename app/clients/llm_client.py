class LLMClient:
    def complete(self, prompt: str) -> str:
        return f"MOCK_RESPONSE: {prompt[:120]}"
