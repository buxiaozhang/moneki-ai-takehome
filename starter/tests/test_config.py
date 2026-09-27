"""大模型配置的读取规则。

以前只有 `make run` 一条路能跑，配置没配上就只显示一个 mock，
看不出是"没读进来"还是"读进来了但是空的"。这里的测试把读取链路钉死。
"""

from __future__ import annotations

import os

import pytest

from kbqa import config


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """每个用例都从"三个变量都没有"开始，避免互相污染。"""
    for name in ("LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL", "KBQA_NO_DOTENV"):
        monkeypatch.delenv(name, raising=False)
    yield


# -- .env 解析 -----------------------------------------------------------------


def test_parse_basic():
    values = config.parse_dotenv(
        "LLM_BASE_URL=https://api.deepseek.com\nLLM_API_KEY=sk-x\nLLM_MODEL=deepseek-flash\n"
    )
    assert values == {
        "LLM_BASE_URL": "https://api.deepseek.com",
        "LLM_API_KEY": "sk-x",
        "LLM_MODEL": "deepseek-flash",
    }


def test_parse_ignores_comments_and_blanks():
    values = config.parse_dotenv("# 注释\n\n  \nA=1\n")
    assert values == {"A": "1"}


def test_parse_strips_quotes_and_export_prefix():
    values = config.parse_dotenv('export LLM_MODEL="deepseek-flash"\nB=\'x\'\n')
    assert values == {"LLM_MODEL": "deepseek-flash", "B": "x"}


def test_parse_tolerates_bom():
    """Windows 的 `Set-Content -Encoding utf8` 会写 BOM。

    不去掉的话第一个键会变成 `\\ufeffLLM_BASE_URL`，表现就是"明明配了却读不到"。
    """
    values = config.parse_dotenv("\ufeffLLM_BASE_URL=https://api.deepseek.com\n")
    assert values == {"LLM_BASE_URL": "https://api.deepseek.com"}


def test_parse_keeps_value_with_equals():
    values = config.parse_dotenv("URL=https://x.example/a?b=1\n")
    assert values["URL"] == "https://x.example/a?b=1"


# -- .env 加载 -----------------------------------------------------------------


def test_load_dotenv_sets_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("KBQA_DOTENV_PATH", str(tmp_path))
    env_file = tmp_path / ".env"
    env_file.write_text("LLM_MODEL=deepseek-flash\n", encoding="utf-8")
    applied = config.load_dotenv(env_file)
    assert applied == {"LLM_MODEL": "deepseek-flash"}
    assert os.environ["LLM_MODEL"] == "deepseek-flash"


def test_env_var_beats_dotenv(tmp_path, monkeypatch):
    """契约 §7.1：评审用环境变量接管，不能被本机 .env 盖掉。"""
    monkeypatch.setenv("LLM_MODEL", "model-from-env")
    env_file = tmp_path / ".env"
    env_file.write_text("LLM_MODEL=model-from-dotenv\nLLM_API_KEY=key-from-dotenv\n", encoding="utf-8")
    config.load_dotenv(env_file)
    assert os.environ["LLM_MODEL"] == "model-from-env"      # 环境变量赢
    assert os.environ["LLM_API_KEY"] == "key-from-dotenv"   # 没设的才补上


def test_no_dotenv_switch(tmp_path, monkeypatch):
    """设了 KBQA_NO_DOTENV 就完全不读 .env，方便验证"只靠环境变量能不能起来"。"""
    monkeypatch.setenv("KBQA_NO_DOTENV", "1")
    env_file = tmp_path / ".env"
    env_file.write_text("LLM_MODEL=deepseek-flash\n", encoding="utf-8")
    assert config.load_dotenv(env_file) == {}
    assert "LLM_MODEL" not in os.environ


# -- 降级模式 ------------------------------------------------------------------


def test_mock_when_nothing_set(monkeypatch):
    # "什么都没配"要连 .env 也算上：开发机根目录有一份真实 .env 时，
    # load_settings() 会读到它，那就不是"没配"了。
    monkeypatch.setenv("KBQA_NO_DOTENV", "1")
    settings = config.load_settings()
    assert settings.llm_mode == "mock"
    assert set(settings.llm_missing) == {"LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL"}


def test_mock_when_only_key_missing(monkeypatch):
    monkeypatch.setenv("KBQA_NO_DOTENV", "1")
    monkeypatch.setenv("LLM_BASE_URL", "https://api.deepseek.com")
    monkeypatch.setenv("LLM_MODEL", "deepseek-flash")
    settings = config.load_settings()
    assert settings.llm_mode == "mock"
    assert settings.llm_missing == ["LLM_API_KEY"], "要指名道姓说缺哪个，不能只说 mock"


def test_live_when_all_set(monkeypatch):
    monkeypatch.setenv("LLM_BASE_URL", "https://api.deepseek.com")
    monkeypatch.setenv("LLM_API_KEY", "sk-x")
    monkeypatch.setenv("LLM_MODEL", "deepseek-flash")
    settings = config.load_settings()
    assert settings.llm_mode == "live"
    assert settings.llm_missing == []


def test_base_url_is_not_rewritten(monkeypatch):
    """契约 §7.1：地址原样用，不补 /v1、不截路径。"""
    monkeypatch.setenv("LLM_BASE_URL", "https://proxy.example/prefix/")
    monkeypatch.setenv("LLM_API_KEY", "sk-x")
    monkeypatch.setenv("LLM_MODEL", "deepseek-flash")
    settings = config.load_settings()
    # 只去掉结尾的斜杠，路径前缀必须留着
    assert settings.llm_base_url == "https://proxy.example/prefix"


# -- 诊断信息 ------------------------------------------------------------------


def test_diagnostics_never_leaks_key(monkeypatch):
    monkeypatch.setenv("LLM_BASE_URL", "https://api.deepseek.com")
    monkeypatch.setenv("LLM_API_KEY", "sk-super-secret-value")
    monkeypatch.setenv("LLM_MODEL", "deepseek-flash")
    blob = str(config.load_settings().llm_diagnostics())
    assert "sk-super-secret-value" not in blob, "诊断信息里绝不能出现 Key 本身"
    assert "api_key_set" in blob


def test_diagnostics_names_missing(monkeypatch):
    monkeypatch.setenv("KBQA_NO_DOTENV", "1")
    monkeypatch.setenv("LLM_MODEL", "deepseek-flash")
    data = config.load_settings().llm_diagnostics()
    assert data["mode"] == "mock"
    assert "LLM_API_KEY" in data["missing"]
    assert "LLM_BASE_URL" in data["missing"]
    assert data["hint"], "要给出可执行的修复提示"


def test_hint_mentions_restart(monkeypatch):
    """最常见的误区：改了配置不重启，以为没生效。提示里必须说清。"""
    monkeypatch.setenv("KBQA_NO_DOTENV", "1")
    data = config.load_settings().llm_diagnostics()
    assert "重启" in data["hint"] or "启动" in data["hint"]


def test_no_startup_validation_of_key(monkeypatch):
    """契约 §7.2：不要在启动时校验 Key 的格式。

    给一个明显不像 Key 的值，也必须照常进 live —— 具体报错留给第一次真实调用。
    """
    monkeypatch.setenv("LLM_BASE_URL", "https://api.deepseek.com")
    monkeypatch.setenv("LLM_API_KEY", "not-a-key-at-all")
    monkeypatch.setenv("LLM_MODEL", "deepseek-flash")
    settings = config.load_settings()
    assert settings.llm_mode == "live"
