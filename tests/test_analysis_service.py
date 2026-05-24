import pytest
from unittest.mock import MagicMock, patch

from app.services.analysis_service import AnalysisService


def test_analysis_prompt_loading_and_formatting():
    """测试分析总结 Prompt 模板能读取并填充核心输入"""
    with patch.dict("os.environ", {"OPENAI_API_KEY": "dummy_key"}):
        service = AnalysisService()
        template = service._load_prompt_template()

        assert "{question}" in template
        assert "{sql}" in template
        assert "{query_result}" in template

        rendered = template.format(
            question="2022 年各厂商销量排名如何？",
            sql="SELECT manufacturer_name, total_sales FROM t LIMIT 5",
            query_result='{"columns": ["manufacturer_name", "total_sales"]}',
        )

        assert "2022 年各厂商销量排名如何？" in rendered
        assert "SELECT manufacturer_name" in rendered
        assert "manufacturer_name" in rendered


def test_analysis_prompt_contains_required_output_contract():
    """测试 Prompt 明确要求输出核心结论、数据依据和行动建议"""
    with patch.dict("os.environ", {"OPENAI_API_KEY": "dummy_key"}):
        service = AnalysisService()
        template = service._load_prompt_template()

        required_fragments = [
            "core_conclusion",
            "data_evidence",
            "action_suggestions",
            "只能基于查询结果",
            "不要编造",
        ]

        for fragment in required_fragments:
            assert fragment in template


@patch("app.services.analysis_service.dotenv.load_dotenv")
def test_analysis_service_missing_api_key(mock_load_dotenv):
    """测试缺少 API Key 时实例化会失败"""
    with patch.dict("os.environ", {}, clear=True):
        with pytest.raises(ValueError) as excinfo:
            AnalysisService()

        assert "OPENAI_API_KEY" in str(excinfo.value)


@patch("app.services.analysis_service.OpenAI")
def test_analysis_service_mocked_success(mock_openai_class):
    """模拟大模型返回，测试分析总结解析和格式化"""
    with patch.dict("os.environ", {"OPENAI_API_KEY": "dummy_key"}):
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client

        mock_message = MagicMock()
        mock_message.content = (
            '{"core_conclusion": "比亚迪在样例结果中销量最高。", '
            '"data_evidence": "查询结果显示比亚迪销量为 1860000，特斯拉为 710000。", '
            '"action_suggestions": ["持续跟踪头部厂商月度变化", "补充同比增速判断增长质量"]}'
        )
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=mock_message)]
        mock_client.chat.completions.create.return_value = mock_response

        service = AnalysisService()
        analysis = service.generate_analysis(
            question="2022 年各厂商新能源汽车销量排名如何？",
            sql=(
                "SELECT manufacturer_name, SUM(sales_current_units) AS total_sales "
                "FROM fact_nev_manufacturer_monthly GROUP BY manufacturer_name LIMIT 5"
            ),
            columns=["manufacturer_name", "total_sales"],
            rows=[["比亚迪", 1860000], ["特斯拉", 710000]],
        )

        mock_client.chat.completions.create.assert_called_once()
        kwargs = mock_client.chat.completions.create.call_args[1]
        assert kwargs["response_format"] == {"type": "json_object"}
        assert kwargs["temperature"] == 0.2
        assert kwargs["messages"][0] == {
            "role": "system",
            "content": "你是一名专业的 BI 数据分析师。",
        }

        prompt = kwargs["messages"][1]["content"]
        assert "2022 年各厂商新能源汽车销量排名如何？" in prompt
        assert "fact_nev_manufacturer_monthly" in prompt
        assert "比亚迪" in prompt

        assert "核心结论：比亚迪在样例结果中销量最高。" in analysis
        assert "数据依据：查询结果显示比亚迪销量为 1860000，特斯拉为 710000。" in analysis
        assert "1. 持续跟踪头部厂商月度变化" in analysis
        assert "2. 补充同比增速判断增长质量" in analysis


@patch("app.services.analysis_service.OpenAI")
def test_analysis_service_rejects_missing_required_json_fields(mock_openai_class):
    """测试大模型缺少必要字段时服务会报错"""
    with patch.dict("os.environ", {"OPENAI_API_KEY": "dummy_key"}):
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client

        mock_message = MagicMock()
        mock_message.content = '{"core_conclusion": "只有结论"}'
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=mock_message)]
        mock_client.chat.completions.create.return_value = mock_response

        service = AnalysisService()

        with pytest.raises(ValueError, match="data_evidence"):
            service.generate_analysis(
                question="问题",
                sql="SELECT 1",
                columns=["x"],
                rows=[[1]],
            )


def test_format_query_result_truncates_long_result():
    """测试长查询结果会截断，避免 Prompt 过长"""
    with patch.dict("os.environ", {"OPENAI_API_KEY": "dummy_key"}):
        service = AnalysisService(max_result_rows=2)

        formatted = service._format_query_result(
            columns=["rank", "brand"],
            rows=[[1, "比亚迪"], [2, "特斯拉"], [3, "广汽埃安"]],
        )

        assert '"row_count": 3' in formatted
        assert '"truncated": true' in formatted
        assert "广汽埃安" not in formatted
