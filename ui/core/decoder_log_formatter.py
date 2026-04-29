from __future__ import annotations

import json
from typing import Any, Dict


def summarize_decoder_session_info(params: Dict[str, Any]) -> str:
    """
    给 decoder.session_info 做一个“尽量通用”的摘要，避免直接 dump 大体积波形。
    """
    try:
        keys = list(params.keys())[:30]
    except Exception:
        keys = []

    channels = None
    samples = None

    candidates = []
    for k in ("eeg", "waveform", "data", "channels"):
        v = params.get(k)
        if v is not None:
            candidates.append((k, v))

    for _, v in candidates:
        if isinstance(v, list) and v and all(isinstance(x, list) for x in v):
            channels = len(v)
            try:
                samples = max((len(x) for x in v if isinstance(x, list)), default=None)
            except Exception:
                samples = None
            break
        if isinstance(v, dict):
            ch = v.get("channels") or v.get("channel_names") or v.get("ch_names")
            dat = v.get("data") or v.get("samples") or v.get("wave")
            if isinstance(ch, list):
                channels = len(ch)
            if isinstance(dat, list) and dat and all(isinstance(x, list) for x in dat):
                channels = channels or len(dat)
                try:
                    samples = max((len(x) for x in dat if isinstance(x, list)), default=None)
                except Exception:
                    samples = None
            if channels is not None or samples is not None:
                break

    parts = []
    if keys:
        parts.append(f"keys={keys}")
    if channels is not None:
        parts.append(f"channels={channels}")
    if samples is not None:
        parts.append(f"samples={samples}")
    if not parts:
        parts.append("params=<unavailable>")
    return ", ".join(parts)


def log_json(logger, title: str, params: Dict[str, Any]) -> None:
    try:
        logger.info(f"收到 {title}: params={json.dumps(params, ensure_ascii=False)}")
    except Exception:
        logger.info(f"收到 {title}: params={params}")
