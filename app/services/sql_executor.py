import duckdb
from typing import List, Any, Tuple

class SQLExecutor:
    """
    DuckDB SQL 执行器，负责在只读模式下安全地运行 SQL 查询。
    """
    def __init__(self, db_path: str = "data/autobi.duckdb"):
        self.db_path = db_path

    def execute(self, sql: str) -> Tuple[List[str], List[List[Any]]]:
        """
        执行一条 SQL 查询语句。

        参数:
            sql: 待执行的 SQL 查询字符串。

        返回:
            一个元组 (columns, rows):
                - columns: 包含字段名（表头）的列表。
                - rows: 包含每一行数据的二维列表。

        异常:
            duckdb.Error: 当 SQL 语法错误或执行失败时抛出。
        """
        # 内存数据库（:memory:）不能以只读模式启动；对于物理数据库，使用只读模式以支持并发访问并防止文件锁定
        read_only = self.db_path != ":memory:"
        conn = duckdb.connect(self.db_path, read_only=read_only)
        try:
            cursor = conn.cursor()
            cursor.execute(sql)

            # 提取字段名称
            if cursor.description:
                columns = [desc[0] for desc in cursor.description]
            else:
                columns = []

            # 提取所有行数据，并将 tuple 转换为标准的 list 结构以契合 Pydantic 模型
            rows = cursor.fetchall()
            rows_list = [list(row) for row in rows]

            return columns, rows_list
        except Exception as e:
            # 向上层抛出，以便上游接口能捕获错误并将其包装到 JSON 响应的 error_message 中
            raise e
        finally:
            conn.close()
