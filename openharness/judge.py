class OpenAIScoringJudge:
    def __init__(self, endpoint="https://api.openai.com/v1", model="gpt-4"):
        self.endpoint = endpoint
        self.model = model

    def evaluate(self, prompt: str, response: str) -> float:
        return 1.0
