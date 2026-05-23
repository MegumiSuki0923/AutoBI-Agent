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
            "vehicle_category = '总计' AND vehicle_segment = '总计' AND fuel_type = '总计'",
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
        mock_message.content = '{"sql": "SELECT * FROM fact_vehicle_prod_sales_monthly LIMIT 10;", "reason": "简单查询示例"}'
        mock_response.choices = [MagicMock(message=mock_message)]

        # 2. 调用服务
        service = TextToSQLService()
        sql, reason = service.generate_sql(
            question="查询销量",
            schema_context="schema",
            metric_context="metric"
        )

        # 3. 校验调用传参与结果解析
        mock_client.chat.completions.create.assert_called_once()
        kwargs = mock_client.chat.completions.create.call_args[1]
        assert kwargs["response_format"] == {"type": "json_object"}
        assert kwargs["temperature"] == 0.1

        assert sql == "SELECT * FROM fact_vehicle_prod_sales_monthly LIMIT 10;"
        assert reason == "简单查询示例"
