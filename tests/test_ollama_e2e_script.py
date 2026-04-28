from pathlib import Path


def test_ollama_e2e_script_exists_and_covers_required_flows():
    script_path = Path("tests/ollama_e2e_integration.sh")

    assert script_path.exists()

    content = script_path.read_text(encoding="utf-8")

    assert "kbase reset" in content
    assert "kbase ingest" in content
    assert "kbase query" in content
    assert "--only-cache" in content
    assert "--iterative" in content
    assert "qwen3.5-opus" in content
