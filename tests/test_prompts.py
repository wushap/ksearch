"""Tests for prompt templates."""

from ksearch.content_optimization.prompts import (
    format_evaluation_prompt,
    format_refine_prompt,
    format_synthesis_prompt,
)


def test_format_evaluation_prompt():
    system, user = format_evaluation_prompt("python asyncio", "Some content about asyncio")
    assert "python asyncio" in user
    assert "Some content about asyncio" in user
    assert "REFINE" in user
    assert "COMPLETE" in user
    assert len(system) > 0


def test_format_refine_prompt():
    system, user = format_refine_prompt("python asyncio", ["missing error handling", "no examples"])
    assert "missing error handling" in user
    assert "no examples" in user
    assert "refinement_query" in user


def test_format_synthesis_prompt():
    system, user = format_synthesis_prompt("python asyncio", "Raw content here")
    assert "python asyncio" in user
    assert "Raw content here" in user
    assert len(system) > 0
