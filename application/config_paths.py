from __future__ import annotations

from pathlib import Path


def project_root() -> Path:
    """BCI_FES 仓库根目录（与 main.py 所在目录一致）。"""
    return Path(__file__).resolve().parent.parent


def resolve_config_path(raw: str | None) -> str:
    """
    将配置中的可执行路径解析为绝对路径。
    支持前缀 @runtime/ 与 runtime/（均相对仓库根下的 runtime 目录）。
    其余字符串原样返回（兼容仍为绝对路径的旧配置）。
    """
    s = str(raw or "").strip()
    if not s:
        return ""
    key = s.replace("\\", "/")
    root = project_root()
    if key.startswith("@runtime/"):
        rel = key[len("@runtime/") :]
        return str((root / "runtime" / rel).resolve())
    head, sep, tail = key.partition("/")
    if sep and head.lower() == "runtime":
        return str((root / "runtime" / tail).resolve())
    return s
