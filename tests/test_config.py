from pathlib import Path

from app.config import load_project_anthropic_api_key


def test_load_project_anthropic_api_key_from_bare_secret(tmp_path: Path) -> None:
    path = tmp_path / "Anthropic_API_Key.txt"
    path.write_text("sk-ant-test-secret\n", encoding="utf-8")

    assert load_project_anthropic_api_key(path) == "sk-ant-test-secret"


def test_load_project_anthropic_api_key_from_env_style_file(tmp_path: Path) -> None:
    path = tmp_path / "Anthropic_API_Key.txt"
    path.write_text(
        "# local secret\nANTHROPIC_API_KEY='sk-ant-test-secret'\n",
        encoding="utf-8",
    )

    assert load_project_anthropic_api_key(path) == "sk-ant-test-secret"
