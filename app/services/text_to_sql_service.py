import os
import json
import dotenv
from pathlib import Path
from typing import Optional, Tuple
from openai import OpenAI

class TextToSQLService:
    """
    Text-to-SQL 服务，负责连接 LLM (如 DeepSeek, OpenAI)
    将用户输入的自然语言通过 RAG 上下文翻译为可在 Doris 执行的 SQL 查询。
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

    def generate_sql(self, question: str, schema_context: str, metric_context: str, history: Optional[list] = None) -> Tuple[bool, Optional[str], str, Optional[str]]:
        """
        利用 LLM 进行意图判定和 SQL 生成。

        参数:
            question: 用户的自然语言提问。
            schema_context: RAG 召回的数据库表结构信息。
            metric_context: RAG 召回的指标口径定义信息。

        返回:
            一个四元组 (is_data_query, sql, reason, chat_reply):
                - is_data_query: 是否是真实可执行的数据查询。
                - sql: LLM 生成的只读 SQL 语句（非数据查询时为 None）。
                - reason: LLM 编写的查询逻辑解释（或无法查询的原因）。
                - chat_reply: 针对非数据查询生成的对话回复（数据查询时为 None）。
        """
        # 1. 加载并填充模板
        template = self._load_prompt_template()
        prompt = template.format(
            question=question,
            schema_context=schema_context,
            metric_context=metric_context
        )

        try:
            messages = [{
                "role": "system",
                "content": (
                    "You are a professional database developer and BI analyst. "
                    "Use the same-session conversation context to resolve follow-up references such as "
                    "'他们', '这三家', '上述厂商', or '这些车型'. When historical result rows identify entities, "
                    "carry those entities into the new SQL as explicit filters such as IN (...)."
                ),
            }]
            if history:
                for h in history:
                    messages.append({"role": h.get("role", "user"), "content": h.get("content", "")})
            messages.append({"role": "user", "content": prompt})

            # 2. 调用 LLM
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                # 开启 JSON 模式，强制大模型必须且仅输出合法的 JSON
                response_format={"type": "json_object"},
                temperature=0.1  # 调低随机度，使 SQL 生成结果更加稳定
            )

            # 3. 解析模型输出
            raw_content = response.choices[0].message.content
            data = json.loads(raw_content)

            is_data_query = data.get("is_data_query", True)
            if isinstance(is_data_query, str):
                is_data_query = is_data_query.lower() == "true"
            is_data_query = bool(is_data_query)

            sql = data.get("sql")
            if sql:
                sql = sql.strip()

            reason = data.get("reason", "").strip()

            chat_reply = data.get("chat_reply")
            if chat_reply:
                chat_reply = chat_reply.strip()

            # 容错处理：若是数据查询但 sql 为空
            if is_data_query and not sql:
                is_data_query = False
                if not chat_reply:
                    chat_reply = "抱歉，我未能为您生成用于执行该查询的 SQL。"

            return is_data_query, sql, reason, chat_reply

        except json.JSONDecodeError as je:
            raise ValueError(f"大模型返回的数据不是合法的 JSON 格式: {raw_content}") from je
        except Exception as e:
            raise RuntimeError(f"Text-to-SQL 服务在大模型调用过程中发生错误: {str(e)}") from e

    def repair_sql(
        self,
        *,
        question: str,
        failed_sql: str,
        error_message: str,
        schema_context: str,
        metric_context: str,
        history: Optional[list] = None,
    ) -> Tuple[str, str]:
        """
        根据 SQL Guard 或 Doris 执行错误修复候选 SQL。

        返回:
            一个二元组 (sql, reason):
                - sql: 修复后的只读 SQL，后续仍必须经过 SQLGuard 校验。
                - reason: 修复思路说明。
        """
        prompt = f"""
你是企业数据平台的 SQL 修复助手。请根据用户问题、同会话上下文、表结构、指标口径、失败 SQL 和错误信息，修复出一条可在 Apache Doris 执行的只读 SQL。

## 用户问题
{question}

## 相关表结构设计 (Schema Context)
{schema_context}

## 相关指标口径 (Metric Context)
{metric_context}

## 失败 SQL
{failed_sql}

## 错误信息
{error_message}

## 修复规则
1. 只能返回只读查询，顶层必须是 `SELECT` 或 `WITH ... SELECT`。
2. 只能使用 Schema Context 中明确出现的表名和字段名。
3. 保持用户原始业务意图，不要改成无关查询。
4. 如果错误来自 SQL Guard，必须修复 Guard 提到的安全或语法问题。
5. 如果错误来自 Doris 执行器，必须修复字段、函数、聚合、方言或表选择问题。
6. 必须显式列出字段，禁止 `SELECT *`。
7. 默认添加 `LIMIT 100`，除非用户明确要求其它返回数量。

请返回纯 JSON，且只能包含以下两个键：
- `sql`: 修复后的 SQL 字符串。
- `reason`: 简短说明修复了什么。
"""

        try:
            messages = [{
                "role": "system",
                "content": (
                    "You repair Apache Doris SQL for a BI Text-to-SQL system. "
                    "Return only safe read-only SQL in JSON. The repaired SQL will be checked by SQLGuard before execution."
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
                temperature=0.0,
            )

            raw_content = response.choices[0].message.content
            data = json.loads(raw_content)
            sql = data.get("sql")
            reason = data.get("reason", "")

            if not isinstance(sql, str) or not sql.strip():
                raise ValueError("大模型未返回可用于修复的 SQL。")

            return sql.strip(), str(reason).strip()

        except json.JSONDecodeError as je:
            raise ValueError(f"大模型返回的 SQL 修复结果不是合法 JSON: {raw_content}") from je
        except Exception as e:
            raise RuntimeError(f"SQL 自动修复过程中发生错误: {str(e)}") from e
