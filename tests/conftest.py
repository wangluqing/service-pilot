import pytest


@pytest.fixture(autouse=True)
def force_rules_mode(monkeypatch):
    """每个测试默认走规则模式，避免套件访问外部模型。

    @param monkeypatch - pytest 环境变量补丁
    """

    monkeypatch.setenv("SP_MODE", "rules")
    monkeypatch.setenv("SP_LLM_FALLBACK", "off")
    monkeypatch.setenv("SP_REAL_LLM_WEB_AUTHORIZED", "false")
