import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(BACKEND_ROOT / ".env")

DEFAULT_BASE_URL = "https://api.groq.com/openai/v1"


class GroqService:
    def __init__(self) -> None:
        self.api_key = os.getenv("GROQ_API_KEY")
        self.base_url = os.getenv("GROQ_BASE_URL") or DEFAULT_BASE_URL
        self.model = os.getenv("GROQ_MODEL")

    def generate_response(self, prompt: str) -> str:
        missing = [
            name
            for name, value in (
                ("GROQ_API_KEY", self.api_key),
                ("GROQ_MODEL", self.model),
            )
            if not value
        ]
        if missing:
            raise ValueError(f"Missing required Groq configuration: {', '.join(missing)}.")

        client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        response = client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content or ""


groq_service = GroqService()


def generate_response(prompt: str) -> str:
    return groq_service.generate_response(prompt)