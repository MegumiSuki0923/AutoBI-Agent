import os
import json
import dotenv
from pathlib import Path
from typing import Tuple
from openai import OpenAI

class TextToSQLService:
    """
    Text-to-SQL 服务，负责连接 LLM (如 DeepSeek, OpenAI)
    将用户输入的自然语言通过 RAG 上下文翻译为可在 DuckDB 执行的 SQL 查询。
    """
    def __init__(self, prompt_path: str = "app/prompts/text_to_sql_prompt.md"):
        # 1. 加载本地 .env 环境配置
        dotenv.load_dotenv()

        self.prompt_path = prompt_path
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        self.model = os.getenv("LLM_MODEL", "deepseek-chat")

        # 2. 检查关键配置
        if not self.api_key:
            raise ValueError(
                "未在环境变量或 .env 文件中发现 OPENAI_API_KEY！\n"
                "请在项目根目录的 .env 文件中配置：\n"
                "OPENAI_API_KEY=你的密钥\n"
                "OPENAI_BASE_URL=API地址"
            )

        # 3. 初始化 OpenAI 兼容客户端
        self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)

    def _load_prompt_template(self) -> str:
        """加载 Prompt 模板文件"""
        p = Path(self.prompt_path)
        if not p.exists():
            raise FileNotFoundError(f"未找到 Text-to-SQL Prompt 模板文件: {self.prompt_path}")
        return p.read_text(encoding="utf-8")

    def generate_sql(self, question: str, schema_context: str, metric_context: str) -> Tuple[str, str]:
        """
        利用 LLM 生成 SQL 和解释。

        参数:
            question: 用户的自然语言提问。
            schema_context: RAG 召回的数据库表结构信息。
            metric_context: RAG 召回的指标口径定义信息。

        返回:
            一个元组 (sql, reason):
                - sql: LLM 生成的只读 SQL 语句。
                - reason: LLM 编写的查询逻辑解释。
        """
        # 1. 加载并填充模板
        template = self._load_prompt_template()
        prompt = template.format(
            question=question,
            schema_context=schema_context,
            metric_context=metric_context
        )

        try:
            # 2. 调用 LLM
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a professional database developer and BI analyst."},
                    {"role": "user", "content": prompt}
                ],
                # 开启 JSON 模式，强制大模型必须且仅输出合法的 JSON
                response_format={"type": "json_object"},
                temperature=0.1  # 调低随机度，使 SQL 生成结果更加稳定
            )

            # 3. 解析模型输出
            raw_content = response.choices[0].message.content
            data = json.loads(raw_content)

            sql = data.get("sql", "").strip()
            reason = data.get("reason", "").strip()

            if not sql:
                raise ValueError("大模型响应的 JSON 中不包含 'sql' 字段")

            return sql, reason

        except json.JSONDecodeError as je:
            raise ValueError(f"大模型返回的数据不是合法的 JSON 格式: {raw_content}") from je
        except Exception as e:
            raise RuntimeError(f"Text-to-SQL 服务在大模型调用过程中发生错误: {str(e)}") from e
