"""Query classification helpers for iterative search."""


class QueryClassifier:
    """Classifies search queries as fact-seeking or exploration queries."""

    FACT_KEYWORDS = [
        "如何", "是什么", "定义", "怎么", "怎样",
        "how to", "what is", "definition", "who is", "when",
        "where", "what are", "explain",
    ]

    EXPLORATION_KEYWORDS = [
        "探索", "研究", "对比", "分析", "综述",
        "explore", "compare", "analyze", "review", "overview",
        "survey", "investigate", "deep dive",
    ]

    def classify(self, query: str) -> str:
        query_lower = query.lower().strip()
        word_count = len(query.split())

        for keyword in self.EXPLORATION_KEYWORDS:
            if keyword in query_lower:
                return "exploration"

        for keyword in self.FACT_KEYWORDS:
            if keyword in query_lower:
                return "fact"

        if word_count < 5:
            return "fact"
        return "exploration"


__all__ = ["QueryClassifier"]
