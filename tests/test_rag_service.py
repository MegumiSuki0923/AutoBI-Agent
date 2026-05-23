import pytest
from app.services.rag_service import RAGService

@pytest.fixture
def rag_service():
    # 实例化 RAG 服务，默认读取本地 docs 目录下的 markdown 文档
    return RAGService()

def test_rag_service_loading(rag_service):
    """测试文档加载与切分功能是否正常"""
    chunks = rag_service.chunks
    assert len(chunks) > 0, "切分出的 Chunk 数量不能为 0"

    # 验证 Chunk 的基本属性结构
    for chunk in chunks:
        assert "id" in chunk
        assert "title" in chunk
        assert "content" in chunk
        assert "source" in chunk
        assert chunk["source"] in ["data_dictionary.md", "metrics.md"]

def test_rag_service_retrieve_nev_penetration(rag_service):
    """测试输入新能源渗透率，能够正确召回对应的指标口径"""
    query = "2022 年新能源汽车渗透率的月度趋势如何？"
    results = rag_service.retrieve(query, limit=3)

    assert len(results) > 0
    # 检查返回的结果中，首个或者前几个结果中是否包含了“渗透率”或渗透率的事实表名称
    titles = [chunk["title"] for chunk in results]

    # 必须召回“4.8 新能源渗透率”这个指标定义或包含它的表
    has_penetration = any("渗透率" in t for t in titles)
    assert has_penetration, f"检索结果中未包含渗透率相关指标: {titles}"

def test_rag_service_retrieve_charging(rag_service):
    """测试输入充电设施，能正确召回对应的表结构和指标定义"""
    query = "哪些省份的充电设施数量增长最快？"
    results = rag_service.retrieve(query, limit=3)

    assert len(results) > 0
    titles = [chunk["title"] for chunk in results]

    # 检查是否包含了充电设施表（fact_charging_infrastructure_monthly）或充电设施指标口径
    has_charging = any("charging" in t.lower() or "充电" in t for t in titles)
    assert has_charging, f"检索结果中未包含充电设施相关文档: {titles}"

def test_rag_service_empty_query(rag_service):
    """测试空输入防御逻辑"""
    assert rag_service.retrieve("") == []
    assert rag_service.retrieve("   ") == []
    assert rag_service.retrieve(None) == []
