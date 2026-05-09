"""Prompt templates for content optimization."""


def format_evaluation_prompt(query: str, results_text: str) -> tuple[str, str]:
    """Return (system_prompt, user_prompt) for quality evaluation."""
    system = (
        "You are a research quality evaluator. Assess search results for completeness, "
        "accuracy, and relevance. Be critical and identify specific gaps. "
        "Always respond with valid JSON only, no other text."
    )
    user = (
        f'Evaluate the following search results for the query: "{query}"\n\n'
        f"Search Results:\n{results_text}\n\n"
        "Respond in this exact JSON format:\n"
        '{\n'
        '  "action": "REFINE or COMPLETE",\n'
        '  "confidence": 0.0 to 1.0,\n'
        '  "gaps": ["gap1", "gap2"],\n'
        '  "refinement_query": "targeted query to fill the most important gap",\n'
        '  "summary": "brief quality assessment"\n'
        '}'
    )
    return system, user


def format_refine_prompt(query: str, gaps: list[str]) -> tuple[str, str]:
    """Return (system_prompt, user_prompt) for refinement query generation."""
    system = (
        "You are a research assistant. Generate a targeted search query to fill "
        "identified information gaps. Always respond with valid JSON only."
    )
    gaps_text = "\n".join(f"- {gap}" for gap in gaps)
    user = (
        f'Original query: "{query}"\n\n'
        f"Identified gaps:\n{gaps_text}\n\n"
        "Generate a targeted follow-up search query.\n"
        "Respond in this exact JSON format:\n"
        '{\n'
        '  "refinement_query": "the search query",\n'
        '  "rationale": "why this query fills the gaps"\n'
        '}'
    )
    return system, user


def format_synthesis_prompt(query: str, content: str) -> tuple[str, str]:
    """Return (system_prompt, user_prompt) for content synthesis."""
    system = (
        "You are a content synthesizer. Combine research results into a clear, "
        "well-structured summary. Remove redundancy, fix contradictions, "
        "and highlight key findings. Output clean markdown."
    )
    user = (
        f'Synthesize the following research results for the query: "{query}"\n\n'
        f"Raw Results:\n{content}\n\n"
        "Produce a concise, well-organized summary in markdown format."
    )
    return system, user
