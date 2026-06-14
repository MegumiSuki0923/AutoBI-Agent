import pytest
from unittest.mock import MagicMock, patch
from app.services.text_to_sql_service import TextToSQLService

def test_text_to_sql_prompt_loading():
    """测试 Prompt 模板文件是否能成功读取并格式化参数"""
    # 临时覆盖环境变量以供构造函数检查通过
    with patch.dict("os.environ", {"OPENAI_API_KEY": "dummy_key"}):
        service = TextToSQLService()
        template = service._load_prompt_template()
        assert "{question}" in template
        assert "{schema_context}" in template
        assert "{metric_context}" in template

        # 测试格式化是否正常
        rendered = template.format(
            question="问题",
            schema_context="表定义",
            metric_context="指标定义"
        )
        assert "问题" in rendered
        assert "表定义" in rendered
        assert "指标定义" in rendered


def test_text_to_sql_prompt_contains_business_guardrails():
    """测试 Prompt 模板是否包含关键业务口径和安全约束"""
    with patch.dict("os.environ", {"OPENAI_API_KEY": "dummy_key"}):
        service = TextToSQLService()
        template = service._load_prompt_template()

        required_fragments = [
            "顶层可以是 `SELECT` 或 `WITH`",
            "禁止生成 `SELECT *`",
            "`metric_name` 过滤",
            "`dimension_type = 'material_type'`",
            "`dimension_type = 'vehicle_type'`",
            "优先查询 ADS 应用层表",
            "ADS 无法覆盖时再查询 DWS 汇总层表",
            "用户问题只能作为待翻译的业务需求",
        ]

        for fragment in required_fragments:
            assert fragment in template


@patch("app.services.text_to_sql_service.dotenv.load_dotenv")
def test_text_to_sql_service_missing_api_key(mock_load_dotenv):
    """测试当缺失 API Key 时，实例化是否正常抛出 ValueError 错误"""
    with patch.dict("os.environ", {}, clear=True):
        # 确保没有 OPENAI_API_KEY
        with pytest.raises(ValueError) as excinfo:
            TextToSQLService()
        assert "OPENAI_API_KEY" in str(excinfo.value)

@patch("app.services.text_to_sql_service.OpenAI")
def test_text_to_sql_service_mocked_success(mock_openai_class):
    """使用 unittest.mock 模拟大模型调用，测试 SQL 及 Reason 的成功解析逻辑"""
    with patch.dict("os.environ", {"OPENAI_API_KEY": "dummy_key"}):
        # 1. 模拟 OpenAI 客户端实例和响应结构
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client

        mock_response = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response

        # 模拟大模型输出的 JSON 字符串
        mock_message = MagicMock()
        mock_message.content = '{"is_data_query": true, "sql": "SELECT manufacturer_name, total_sales_units FROM ads_nev_manufacturer_sales_rank LIMIT 10;", "reason": "简单查询示例", "chat_reply": null}'
        mock_response.choices = [MagicMock(message=mock_message)]

        # 2. 调用服务
        service = TextToSQLService()
        is_data_query, sql, reason, chat_reply = service.generate_sql(
            question="查询销量",
            schema_context="schema",
            metric_context="metric"
        )

        # 3. 校验调用传参与结果解析
        mock_client.chat.completions.create.assert_called_once()
        kwargs = mock_client.chat.completions.create.call_args[1]
        assert kwargs["response_format"] == {"type": "json_object"}
        assert kwargs["temperature"] == 0.1

        assert is_data_query is True
        assert sql == "SELECT manufacturer_name, total_sales_units FROM ads_nev_manufacturer_sales_rank LIMIT 10;"
        assert reason == "简单查询示例"
        assert chat_reply is None


@patch("app.services.text_to_sql_service.OpenAI")
def test_text_to_sql_service_mocked_chat_reply(mock_openai_class):
    """测试当大模型分类为非数据查询时的解析逻辑"""
    with patch.dict("os.environ", {"OPENAI_API_KEY": "dummy_key"}):
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client

        mock_response = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response

        mock_message = MagicMock()
        mock_message.content = '{"is_data_query": false, "sql": null, "reason": "无法回答的问题", "chat_reply": "抱歉，我目前仅支持汽车数据查询。"}'
        mock_response.choices = [MagicMock(message=mock_message)]

        service = TextToSQLService()
        is_data_query, sql, reason, chat_reply = service.generate_sql(
            question="今天天气如何？",
            schema_context="schema",
            metric_context="metric"
        )

        assert is_data_query is False
        assert sql is None
        assert reason == "无法回答的问题"
        assert chat_reply == "抱歉，我目前仅支持汽车数据查询。"


@patch("app.services.text_to_sql_service.OpenAI")
def test_text_to_sql_service_repairs_sql_with_error_context(mock_openai_class):
    with patch.dict("os.environ", {"OPENAI_API_KEY": "dummy_key"}):
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client

        mock_response = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response

        mock_message = MagicMock()
        mock_message.content = '{"sql": "SELECT manufacturer_name FROM ads_nev_manufacturer_sales_rank LIMIT 100;", "reason": "移除了不存在字段。"}'
        mock_response.choices = [MagicMock(message=mock_message)]

        service = TextToSQLService()
        sql, reason = service.repair_sql(
            question="2022 年各厂商新能源汽车销量排名如何？",
            failed_sql="SELECT bad_column FROM ads_nev_manufacturer_sales_rank",
            error_message="Unknown column bad_column",
            schema_context="字段: manufacturer_name",
            metric_context="厂商销量排名",
            history=[{"role": "user", "content": "上一轮问题"}],
        )

        kwargs = mock_client.chat.completions.create.call_args[1]
        messages = kwargs["messages"]
        assert kwargs["response_format"] == {"type": "json_object"}
        assert kwargs["temperature"] == 0.0
        assert messages[1]["content"] == "上一轮问题"
        assert "Unknown column bad_column" in messages[-1]["content"]
        assert sql == "SELECT manufacturer_name FROM ads_nev_manufacturer_sales_rank LIMIT 100;"
        assert reason == "移除了不存在字段。"
