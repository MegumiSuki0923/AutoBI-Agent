import json
import os
from pathlib import Path
from typing import Any, List

import dotenv
from openai import OpenAI


class AnalysisService:
    """
    结果分析总结服务。

    输入用户问题、SQL 和查询结果，调用 OpenAI 兼容模型生成可直接返回给前端的
    中文 BI 分析总结。
    """

    def __init__(
        self,
        prompt_path: str = "app/prompts/analysis_prompt.md",
        max_result_rows: int = 20,
    ):
        if max_result_rows <= 0:
            raise ValueError("max_result_rows must be greater than 0")

        dotenv.load_dotenv()

        self.prompt_path = prompt_path
        self.max_result_rows = max_result_rows
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        self.model = os.getenv("LLM_MODEL", "deepseek-chat")

        if not self.api_key:
            raise ValueError(
                "未在环境变量或 .env 文件中发现 OPENAI_API_KEY！\n"
                "请在项目根目录的 .env 文件中配置：\n"
                "OPENAI_API_KEY=你的密钥\n"
                "OPENAI_BASE_URL=API地址"
            )

        self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)

    def _load_prompt_template(self) -> str:
        """加载分析总结 Prompt 模板文件。"""
        path = Path(self.prompt_path)
        if not path.exists():
            raise FileNotFoundError(f"未找到分析总结 Prompt 模板文件: {self.prompt_path}")
        return path.read_text(encoding="utf-8")

    def _format_query_result(self, columns: List[str], rows: List[List[Any]]) -> str:
        """将查询结果转成可控长度的 JSON 文本，避免 Prompt 过长。"""
        preview_rows = [list(row) for row in rows[: self.max_result_rows]]
        payload = {
            "columns": columns,
            "rows": preview_rows,
            "row_count": len(rows),
            "shown_row_count": len(preview_rows),
            "truncated": len(rows) > self.max_result_rows,
        }
        return json.dumps(payload, ensure_ascii=False, indent=2, default=str)

    def generate_analysis(
        self,
        question: str,
        sql: str,
        columns: List[str],
        rows: List[List[Any]],
    ) -> str:
        """
        生成结果分析总结。

        返回文本包含三部分：核心结论、数据依据、行动建议。
        """
        template = self._load_prompt_template()
        prompt = template.format(
            question=question,
            sql=sql,
            query_result=self._format_query_result(columns=columns, rows=rows),
        )

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "你是一名专业的 BI 数据分析师。"},
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.2,
            )

            raw_content = response.choices[0].message.content
            data = json.loads(raw_content)
            return self._format_analysis(data)

        except json.JSONDecodeError as exc:
            raise ValueError(f"大模型返回的数据不是合法的 JSON 格式: {raw_content}") from exc
        except ValueError:
            raise
        except Exception as exc:
            raise RuntimeError(f"结果分析总结服务在大模型调用过程中发生错误: {str(exc)}") from exc

    def _format_analysis(self, data: dict[str, Any]) -> str:
        required_fields = ["core_conclusion", "data_evidence", "action_suggestions"]
        for field in required_fields:
            if field not in data:
                raise ValueError(f"大模型响应的 JSON 中不包含 '{field}' 字段")

        core_conclusion = str(data["core_conclusion"]).strip()
        data_evidence = str(data["data_evidence"]).strip()
        action_suggestions = data["action_suggestions"]

        if not core_conclusion:
            raise ValueError("大模型响应的 'core_conclusion' 字段为空")
        if not data_evidence:
            raise ValueError("大模型响应的 'data_evidence' 字段为空")

        if isinstance(action_suggestions, str):
            suggestions = [action_suggestions.strip()] if action_suggestions.strip() else []
        elif isinstance(action_suggestions, list):
            suggestions = [str(item).strip() for item in action_suggestions if str(item).strip()]
        else:
            raise ValueError("大模型响应的 'action_suggestions' 字段必须是字符串或列表")

        if not suggestions:
            raise ValueError("大模型响应的 'action_suggestions' 字段为空")

        suggestion_lines = "\n".join(
            f"{index}. {suggestion}" for index, suggestion in enumerate(suggestions, start=1)
        )

        return (
            f"核心结论：{core_conclusion}\n\n"
            f"数据依据：{data_evidence}\n\n"
            f"行动建议：\n{suggestion_lines}"
        )
