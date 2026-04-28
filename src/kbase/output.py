"""Output formatting module."""


def format_markdown(results: list, keyword: str) -> str:
    """Format results as structured Markdown."""
    lines = []

    lines.append(f"# 搜索结果: \"{keyword}\"")
    lines.append("")

    if not results:
        lines.append("无结果")
        return "\n".join(lines)

    # Separate cached and new results
    cached = [r for r in results if r.cached]
    new = [r for r in results if not r.cached]

    if cached:
        lines.append(f"## 缓存结果 ({len(cached)}条)")
        lines.append("")
        for i, entry in enumerate(cached, 1):
            lines.append(f"### {i}. [cached] {entry.title}")
            lines.append(f"- **URL**: {entry.url}")
            lines.append(f"- **来源**: {entry.source}")
            lines.append(f"- **缓存时间**: {entry.cached_date}")
            lines.append(f"- **文件路径**: {entry.file_path}")
            lines.append("")
            lines.append("---")
            lines.append("")
            lines.append(entry.content)
            lines.append("")
            lines.append("---")
            lines.append("")

    if new:
        lines.append(f"## 网络搜索结果 ({len(new)}条)")
        lines.append("")
        for i, entry in enumerate(new, len(cached) + 1):
            lines.append(f"### {i}. {entry.title}")
            lines.append(f"- **URL**: {entry.url}")
            lines.append(f"- **来源**: {entry.source}")
            lines.append(f"- **文件路径**: {entry.file_path}")
            lines.append("")
            lines.append("---")
            lines.append("")
            lines.append(entry.content)
            lines.append("")
            lines.append("---")
            lines.append("")

    lines.append(f"总计: {len(results)}条结果")

    return "\n".join(lines)


def format_paths(results: list) -> str:
    """Format results as file paths only."""
    if not results:
        return ""

    paths = [r.file_path for r in results]
    return "\n".join(paths) + "\n"