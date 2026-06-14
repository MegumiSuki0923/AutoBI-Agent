import os
import json
import dotenv
from pathlib import Path
from typing import List, Optional
from openai import OpenAI

class TableRoutingService:
    def __init__(self, prompt_path: str = "app/prompts/table_routing_prompt.md"):
        dotenv.load_dotenv()
        self.prompt_path = prompt_path
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        self.model = os.getenv("LLM_MODEL", "deepseek-chat")

        if not self.api_key:
            raise ValueError("Missing OPENAI_API_KEY")
        self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)

    def route_tables(self, question: str, history: Optional[List[dict]] = None) -> List[str]:
        p = Path(self.prompt_path)
        template = p.read_text(encoding="utf-8")
        prompt = template.format(question=question)

        try:
            messages = [{
                "role": "system",
                "content": (
                    "You are a professional database architect. Use same-session history to resolve "
                    "follow-up references such as '他们', '这三家', or '上述厂商' before choosing tables."
                ),
            }]
            if history:
                for h in history:
                    messages.append({"role": h.get("role", "user"), "content": h.get("content", "")})
            messages.append({"role": "user", "content": prompt})

            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                response_format={"type": "json_object"},
                temperature=0.0
            )
            raw_content = response.choices[0].message.content
            data = json.loads(raw_content)
            return data.get("table_names", [])
        except Exception as e:
            raise RuntimeError(f"Table routing failed: {str(e)}") from e
