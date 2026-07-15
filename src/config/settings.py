"""
配置设置
包含默认配置、免责声明等常量
"""

import json
import logging

from src.config.paths import get_config_path
from src.config.io_guard import is_in_battle


logger = logging.getLogger(__name__)

# ============================= 免责声明内容 =============================
DISCLAIMER = """
                ================================================
                |          软件使用免责声明与许可协议               |
                ================================================

一、免责声明
1. 本软件为免费开源项目，按"原样"提供，开发者不提供任何明示或暗示的担保。
2. 使用本软件的风险完全由用户自行承担，开发者对因使用或无法使用本软件导致的任何损失不承担责任。
3. 本软件不构成任何专业建议，用户应自行判断其适用性。

二、许可条款
1. 本软件基于[MIT许可证]开源，用户可自由使用、修改和分发。
2. 禁止任何形式的商业售卖行为，包括但不限于：
   - 出售软件副本或修改版本
   - 提供付费激活服务
   - 捆绑收费服务

三、用户义务
1. 用户承诺不将本软件用于任何非法用途。
2. 用户同意不逆向工程、反编译或试图获取源代码（已开源的除外）。

四、反诈骗声明
制作者从未也永远不会：
- 通过任何渠道要求付款
- 索取账号密码或支付信息

"""

# ============================= 默认配置 =============================
DEFAULT_CONFIG = {
    "adb_port": 5037,
    "extra_templates_dir": "extra_templates",
    "auto_restart": {
        "enabled": True,
        "stage_timeout": 300,   # 5分钟无新阶段超时（秒）
        "max_restarts": 3,       # 自动重启次数上限（再次触发则停脚本）
    },
    "run_settings": {
        "max_run_duration": 0,  # 脚本最大运行时长（秒），0表示不限制
    },
    "devices": [
        {
            "name": "MuMu模拟器",
            "serial": "127.0.0.1:16384",
            "screenshot_deep_color": False,
            "is_global": False
        }
    ],
    "game": {
        "resolution": "720p",  # 支持的分辨率: 720p, 1080p
        "evolution_rounds": [5, 6, 7, 8, 9],  # 进化回合
        "evolution_rounds_with_extra_cost": [4, 5, 6, 7, 8],  # 有额外费用时的进化回合
        "max_follower_count": 5,  # 最大随从数量
        "cost_recognition": {
            "confidence_threshold": 0.6,
            "max_cost": 10,
            "min_cost": 0
        }
    },
    "ui": {
        "notification_enabled": True,
        "log_level": "INFO",
        "save_screenshots": False,
        "debug_mode": False,
        "custom_background": {
            "enabled": False,
            "path": "",
            "opacity": 22
        }
    },
    "templates": {
        "threshold": 0.85,
        "pyramid_levels": 2,
        "edge_thresholds": [50, 200]
    },
    # 策略结构默认不预填效果；档案结构预留给界面组合卡组与策略。
    "profiles": {
        "deck": {"name": "inline", "source": "config.json"},
        "strategy": {"name": "inline", "source": "config.json"},
    },
    "strategy": {
        "effects": {}
    },
}

# ============================= 拖动相关配置 =============================
# 拖动总时间区间（秒），全局统一，(最小值, 最大值)
HUMAN_LIKE_DRAG_DURATION_RANGE_DEFAULT = (0.12, 0.16)

# 可选的运行时配置注入，用于避免重复读取磁盘。
_runtime_config = None
_cached_drag_range = None
_warned_battle_fallback = False


def set_runtime_config(config):
    """注入运行时配置字典，例如 ``ConfigManager.config``。"""
    global _runtime_config
    _runtime_config = config


def _extract_drag_range(config):
    val = None
    try:
        val = config.get("game", {}).get("human_like_drag_duration_range", None)
    except Exception:
        val = None

    if (
        isinstance(val, list)
        and len(val) == 2
        and isinstance(val[0], (int, float))
        and isinstance(val[1], (int, float))
        and 0 < val[0] < val[1] < 10
    ):
        return (float(val[0]), float(val[1]))
    return None

def get_human_like_drag_duration_range():
    # 已注入配置时优先使用内存数据。
    if isinstance(_runtime_config, dict):
        return _extract_drag_range(_runtime_config) or HUMAN_LIKE_DRAG_DURATION_RANGE_DEFAULT

    # 对战热路径中禁止回退到磁盘读取。
    global _warned_battle_fallback
    if is_in_battle():
        if not _warned_battle_fallback:
            _warned_battle_fallback = True
            logger.warning(
                "[IO] battle context: runtime config not injected; "
                "using default drag range without disk read"
            )
        return HUMAN_LIKE_DRAG_DURATION_RANGE_DEFAULT

    global _cached_drag_range
    if _cached_drag_range is not None:
        return _cached_drag_range

    config_path = get_config_path()
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
            _cached_drag_range = _extract_drag_range(config) or HUMAN_LIKE_DRAG_DURATION_RANGE_DEFAULT
            return _cached_drag_range
    except Exception:
        _cached_drag_range = HUMAN_LIKE_DRAG_DURATION_RANGE_DEFAULT
        return _cached_drag_range
