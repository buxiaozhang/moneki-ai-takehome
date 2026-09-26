"""配置：路径、今天、大模型三件套，全部从环境变量读。

三个环境变量就能接管。所以**环境变量优先**这条不能动。
`.env` 只是本机开发的方便：省得每开一个终端都要重新 export 一遍，

想临时忽略 `.env`（例如验证"只配环境变量能不能起来"），设 `KBQA_NO_DOTENV=1`。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Optional

#: 契约规定：系统的“今天”固定为 2026-09-01。
#: 允许用环境变量覆盖，只为测试留一个口子，默认值就是契约值。
DEFAULT_TODAY = "2026-09-01"

PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = PACKAGE_DIR.parent

#: 接大模型需要的三个变量，缺一个就走 mock 降级模式（契约 §7.2）。
LLM_REQUIRED = ("LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL")

_DOTENV_NAMES = (".env", ".env.local")


def _default_workspace() -> Path:
    """data/ 与 knowledge_base/ 在本项目的上一层。"""
    return PROJECT_DIR.parent


def _path_from_env(name: str, fallback: Path) -> Path:
    raw = os.environ.get(name)
    return Path(raw).expanduser().resolve() if raw else fallback.resolve()


# -- .env ----------------------------------------------------------------------


def find_dotenv() -> Optional[Path]:
    """找 `.env`：先看作业包根目录，再看 starter/。找不到返回 None。"""
    for base in (_default_workspace(), PROJECT_DIR):
        for name in _DOTENV_NAMES:
            candidate = base / name
            if candidate.is_file():
                return candidate
    return None


def parse_dotenv(text: str) -> dict[str, str]:
    """极简 `.env` 解析：`KEY=value`、`#` 注释、可选的 `export` 前缀与引号。

    不引第三方依赖——这份作业的评测脚本只依赖标准库，服务端也不该为了读几行
    配置就多装一个包。

    会先去掉 BOM：Windows 上 `Set-Content -Encoding utf8` 写出来的文件带 BOM，
    不去掉的话第一个键会变成 `\\ufeffLLM_BASE_URL`，看起来"配了却读不到"。
    """
    values: dict[str, str] = {}
    for line in text.lstrip("\ufeff").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        key, separator, value = line.partition("=")
        if not separator:
            continue
        key = key.strip()
        if not key:
            continue
        value = value.strip()
        # 去掉成对的引号，方便写带空格的值
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key] = value
    return values


def load_dotenv(path: Optional[Path] = None) -> dict[str, str]:
    """把 `.env` 的值填进 `os.environ`。

    **已存在的环境变量优先**：`setdefault` 保证评测时他们设的三个变量
    不会被本机 `.env` 盖掉（契约 §7.1）。
    """
    if os.environ.get("KBQA_NO_DOTENV"):
        return {}
    target = path or find_dotenv()
    if target is None:
        return {}
    try:
        # utf-8-sig：自动吃掉 BOM（PowerShell 的 Set-Content 会写 BOM）。
        values = parse_dotenv(target.read_text(encoding="utf-8-sig"))
    except OSError:
        return {}
    applied: dict[str, str] = {}
    for key, value in values.items():
        if key in os.environ:
            continue  # 环境变量优先
        os.environ[key] = value
        applied[key] = value
    return applied


# -- 配置 ----------------------------------------------------------------------


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    kb_dir: Path
    var_dir: Path
    today: date
    llm_base_url: str
    llm_api_key: str
    llm_model: str
    llm_timeout: float
    chat_budget: float
    dotenv_path: Optional[Path] = None

    @property
    def source_db(self) -> Path:
        return self.data_dir / "pos.db"

    @property
    def clean_db(self) -> Path:
        return self.var_dir / "clean.db"

    @property
    def index_path(self) -> Path:
        # 索引缓存跟着仓库走，clone 下来就能直接起服务，不用等建索引。
        return PROJECT_DIR / ".cache" / "index.json"

    @property
    def live(self) -> bool:
        """契约 §7.2：没有 Key 就进入 mock 降级模式，服务照常启动。"""
        return not self.llm_missing

    @property
    def llm_missing(self) -> list[str]:
        """哪几个变量没配上。界面拿它显示"为什么是 mock"，不用猜。"""
        values = {
            "LLM_BASE_URL": self.llm_base_url,
            "LLM_API_KEY": self.llm_api_key,
            "LLM_MODEL": self.llm_model,
        }
        return [name for name in LLM_REQUIRED if not values[name]]

    @property
    def llm_mode(self) -> str:
        return "live" if self.live else "mock"

    def llm_diagnostics(self) -> dict:
        """给界面看的接入状态。

        只报"有没有配"，**绝不回传 Key 本身**（契约 §7.2 第四条）。
        base_url 与 model 不是秘密，露出来方便排查切错地址。
        """
        return {
            "mode": self.llm_mode,
            "missing": self.llm_missing,
            "base_url": self.llm_base_url or None,
            "model": self.llm_model or None,
            "api_key_set": bool(self.llm_api_key),
            "dotenv": str(self.dotenv_path) if self.dotenv_path else None,
            "hint": self._llm_hint(),
        }

    def _llm_hint(self) -> str:
        """一句话说清"为什么是 mock、该怎么修"。"""
        if self.live:
            return "已配置，问答会调用真实模型。"
        names = "、".join(self.llm_missing)
        if self.dotenv_path:
            return (
                "缺少 %s，当前走模板作答。请在这份 .env 里补齐：%s，"
                "然后**重启服务**（配置只在启动时读一次）。"
                % (names, self.dotenv_path)
            )
        return (
            "缺少 %s，当前走模板作答。在作业包根目录放一份 .env"
            "（参考 starter/.env.example），或先设好这三个环境变量再启动服务；"
            "配置只在启动时读一次，改完要重启。" % names
        )


def load_settings() -> Settings:
    applied = load_dotenv()
    workspace = _default_workspace()
    return Settings(
        data_dir=_path_from_env("DATA_DIR", workspace / "data"),
        kb_dir=_path_from_env("KB_DIR", workspace / "knowledge_base"),
        var_dir=_path_from_env("VAR_DIR", PROJECT_DIR / "var"),
        today=date.fromisoformat(os.environ.get("TODAY", DEFAULT_TODAY)),
        # 地址原样使用：不补 /v1，不截路径（契约 §7.2）。
        llm_base_url=os.environ.get("LLM_BASE_URL", "").strip().rstrip("/"),
        llm_api_key=os.environ.get("LLM_API_KEY", "").strip(),
        llm_model=os.environ.get("LLM_MODEL", "").strip(),
        # 契约 §7.3：单次模型调用超时不小于 120 秒。
        llm_timeout=float(os.environ.get("LLM_TIMEOUT", "120")),
        # 契约 §7.3：/api/chat 整体在 180 秒内返回，这里留出余量。
        chat_budget=float(os.environ.get("CHAT_BUDGET", "150")),
        dotenv_path=find_dotenv() if applied else None,
    )
