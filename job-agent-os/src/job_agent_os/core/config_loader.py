"""Configuration file loader with caching.

Loads YAML config files from the project `configs/` directory.
Results are cached in-process; call `clear_config_cache()` in tests
to force a reload.
"""

import logging
import threading
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

# Project root: .../job-agent-os (src/job_agent_os/core/config_loader.py -> 4 levels up)
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_CONFIGS_DIR = _PROJECT_ROOT / "configs"

_cache: dict[str, dict[str, Any]] = {}
_lock = threading.Lock()

# Built-in defaults used when a config file is missing or malformed,
# so that fallback parsing never degrades to "recognize nothing".
_DEFAULT_INTENT_KEYWORDS: dict[str, Any] = {
    "regions": [
        "河南", "郑州", "北京", "上海", "广州", "深圳", "杭州", "成都",
        "武汉", "南京", "洛阳", "开封", "西安", "合肥", "长沙", "重庆",
        "天津", "苏州", "青岛", "大连", "厦门", "宁波",
    ],
    "company_types": ["国企", "央企", "民企", "外企", "事业单位", "上市公司"],
    "directions": [
        "Java", "Python", "Go", "C++", "前端", "后端", "全栈", "算法",
        "机器学习", "大数据", "数据分析", "测试", "运维", "AI", "嵌入式",
    ],
}

_DEFAULT_BOSS_CITY_CODES: dict[str, str] = {
    "全国": "100010000",
    "北京": "101010100",
    "上海": "101020100",
    "广州": "101280100",
    "深圳": "101280600",
    "杭州": "101210100",
    "成都": "101270100",
    "武汉": "101200100",
    "南京": "101190100",
    "郑州": "101180100",
    "西安": "101110100",
    "合肥": "101220100",
    "长沙": "101250100",
    "重庆": "101040100",
    "天津": "101030100",
}


def _load_yaml(filename: str) -> dict[str, Any]:
    """Load a YAML file from the configs directory (cached)."""
    with _lock:
        if filename in _cache:
            return _cache[filename]

        path = _CONFIGS_DIR / filename
        data: dict[str, Any] = {}
        try:
            if path.exists():
                with open(path, encoding="utf-8") as f:
                    loaded = yaml.safe_load(f)
                if isinstance(loaded, dict):
                    data = loaded
                else:
                    logger.warning("Config file %s is not a mapping, ignoring", path)
            else:
                logger.warning("Config file %s not found", path)
        except Exception as e:  # noqa: BLE001
            logger.warning("Failed to load config %s: %s", path, e)

        _cache[filename] = data
        return data


def load_intent_keywords() -> dict[str, list[str]]:
    """Load intent fallback keywords (regions / company_types / directions).

    Returns a dict with the three keyword lists; falls back to built-in
    defaults for any missing section.
    """
    raw = _load_yaml("intent_keywords.yaml")
    return {
        "regions": list(raw.get("regions") or _DEFAULT_INTENT_KEYWORDS["regions"]),
        "company_types": list(
            raw.get("company_types") or _DEFAULT_INTENT_KEYWORDS["company_types"]
        ),
        "directions": list(raw.get("directions") or _DEFAULT_INTENT_KEYWORDS["directions"]),
    }


def load_boss_city_codes() -> dict[str, str]:
    """Load BOSS city name -> numeric city code mapping."""
    raw = _load_yaml("boss_city_codes.yaml")
    codes = raw.get("boss")
    if not isinstance(codes, dict) or not codes:
        return dict(_DEFAULT_BOSS_CITY_CODES)
    return {str(k): str(v) for k, v in codes.items()}


def clear_config_cache() -> None:
    """Clear the in-process config cache (used by tests)."""
    with _lock:
        _cache.clear()
