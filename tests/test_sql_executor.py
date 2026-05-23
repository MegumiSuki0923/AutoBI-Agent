import pytest
import duckdb
from app.services.sql_executor import SQLExecutor

def test_sql_executor_memory_success():
    """测试内存数据库中执行基础 SQL 查询是否成功"""
    executor = SQLExecutor(db_path=":memory:")
    sql = "SELECT 1 AS num, 'Tesla' AS brand UNION ALL SELECT 2, 'BYD';"
    columns, rows = executor.execute(sql)

    # 验证返回结构与值
    assert columns == ["num", "brand"]
    assert rows == [[1, "Tesla"], [2, "BYD"]]
    assert isinstance(rows, list)
    assert isinstance(rows[0], list)

def test_sql_executor_real_db():
    """测试在物理数据表 dim_data_source 上运行查询是否正常"""
    executor = SQLExecutor(db_path="data/autobi.duckdb")
    sql = "SELECT source_id, file_name FROM dim_data_source LIMIT 2;"
    columns, rows = executor.execute(sql)

    # 验证字段和数据
    assert "source_id" in columns
    assert "file_name" in columns
    assert len(rows) > 0
    assert len(rows) <= 2
    for row in rows:
        assert isinstance(row, list)

def test_sql_executor_invalid_sql_syntax():
    """测试当传入错误的 SQL 语法时，执行器是否能正常抛出异常"""
    executor = SQLExecutor(db_path=":memory:")
    sql = "SELECC 1;"  # 错误的关键字 SELECC

    with pytest.raises(duckdb.ParserException):
        executor.execute(sql)

def test_sql_executor_non_existent_table():
    """测试当查询不存在的表时，是否抛出目录异常"""
    executor = SQLExecutor(db_path=":memory:")
    sql = "SELECT * FROM non_existent_table;"

    with pytest.raises(duckdb.CatalogException):
        executor.execute(sql)
