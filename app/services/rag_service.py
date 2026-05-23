import re
from pathlib import Path
from typing import List, Dict, Any, Optional

class RAGService:
    """
    轻量级、完全本地运行的 RAG（检索增强生成）服务。
    通过动态解析数据字典和指标口径 markdown 文档，构建关键词匹配索引库并提供精准检索。
    """
    def __init__(
        self,
        data_dict_path: str = "docs/data_dictionary.md",
        metrics_path: str = "docs/metrics.md"
    ):
        self.data_dict_path = data_dict_path
        self.metrics_path = metrics_path
        self.chunks: List[Dict[str, Any]] = []
        self._load_and_index_documents()

    def _load_and_index_documents(self):
        """解析 markdown 文件，将表格定义与指标口径切分为独立的 Chunk 文档"""
        self.chunks = []

        # 1. 解析数据字典
        data_dict_file = Path(self.data_dict_path)
        if data_dict_file.exists():
            self._parse_markdown_file(data_dict_file, source_name="data_dictionary")

        # 2. 解析指标口径
        metrics_file = Path(self.metrics_path)
        if metrics_file.exists():
            self._parse_markdown_file(metrics_file, source_name="metrics")

    def _parse_markdown_file(self, file_path: Path, source_name: str):
        """按 '### ' 标题进行文档切片"""
        content = file_path.read_text(encoding="utf-8")
        # 正则切分以 '### ' 开头的章节，并捕获标题和章节内容
        # 使用 (?=### ) 可以在保留切分符的同时进行切分
        sections = re.split(r'\n(?=### )', content)

        for idx, sec in enumerate(sections):
            # 处理开头正好是 '### ' 的第一章
            if idx == 0 and sec.startswith("### "):
                sec_text = sec
            elif idx == 0:
                # 忽略文件最前方的 ## 1. / ## 2. 等全局介绍内容
                continue
            else:
                sec_text = sec.strip()

            if not sec_text.startswith("### "):
                continue

            # 提取第一行作为标题，其余作为正文
            lines = sec_text.split("\n")
            title = lines[0].replace("### ", "").strip()
            body = "\n".join(lines[1:]).strip()

            if title and body:
                self.chunks.append({
                    "id": f"{source_name}_{len(self.chunks)}",
                    "title": title,
                    "content": body,
                    "source": file_path.name
                })

    def _tokenize(self, text: str) -> List[str]:
        """
        分词器：提取文本中的核心关键词。
        支持提取：
        1. 英文单词、表名、字段名（如 fact_nev_overall_monthly）。
        2. 中文核心领域词汇（如 渗透率、充电桩 等）。
        3. 单个汉字（防止漏词）。
        """
        text = text.lower()
        tokens = set()

        # 1. 提取所有英文字符、数字和下划线（主要是表名和字段名）
        eng_tokens = re.findall(r'[a-z0-9_]{2,}', text)
        tokens.update(eng_tokens)

        # 2. 提取中文核心领域词（最大匹配匹配）
        domain_keywords = [
            "新能源", "渗透率", "充电桩", "动力电池", "电池", "装车量", "销量",
            "产量", "产销", "占比", "增速", "排行", "排名", "趋势", "结构",
            "纯电", "插混", "省份", "材料", "车型", "厂商", "大类", "统计"
        ]
        for kw in domain_keywords:
            if kw in text:
                tokens.add(kw)

        # 3. 提取单个汉字（用于兜底匹配，过滤掉标点符号和空白）
        chinese_chars = re.findall(r'[\u4e00-\u9fa5]', text)
        tokens.update(chinese_chars)

        return list(tokens)

    def retrieve(self, query: str, limit: int = 3) -> List[Dict[str, Any]]:
        """
        根据用户提出的查询，检索出最相关的表结构或指标口径 Chunk。

        参数:
            query: 用户提问的字符串。
            limit: 返回的最大 Chunk 数量。

        返回:
            排好序的相关 Chunk 字典列表。
        """
        if not query or not query.strip():
            return []

        query_tokens = self._tokenize(query)
        if not query_tokens:
            return []

        scored_chunks = []
        for chunk in self.chunks:
            score = 0
            title_lower = chunk["title"].lower()
            content_lower = chunk["content"].lower()

            # 对每一个查询关键词计算匹配得分
            for token in query_tokens:
                # 1. 标题匹配：标题是极其关键的信息，给予极高权重
                if token in title_lower:
                    # 匹配次数乘以较高权重（标题中通常只出现一次，但也可以计算频次）
                    score += 15 * title_lower.count(token)

                # 2. 正文匹配：常规权重
                if token in content_lower:
                    score += 1 * content_lower.count(token)

            if score > 0:
                scored_chunks.append((score, chunk))

        # 按照得分从高到低排序
        scored_chunks.sort(key=lambda x: x[0], reverse=True)

        # 返回前 limit 个 Chunk
        return [chunk for _, chunk in scored_chunks[:limit]]
