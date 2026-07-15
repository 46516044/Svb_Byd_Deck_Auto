"""卡牌图片文件名辅助函数。

支持在文件名中编码爆能层级。无扩展名时，``4_xxx`` 表示基础费用 4；
``4@6_xxx`` 与 ``4@6@8_xxx`` 分别表示一个或多个爆能费用；同时兼容旧格式
``4_6_xxx`` 与 ``4_6_8_xxx``。卡名本身可以包含下划线，爆能层级只解析基础
费用之后以 ``@`` 分隔的整数段。若解析出的名称形似卡牌 ID，则通过 CSV 还原卡名。
"""

from __future__ import annotations

import csv
import os
import re
from typing import Dict, List, Optional, Tuple

# 全局卡牌 ID 到名称映射，首次访问时延迟加载。
_CARD_ID_MAP: Dict[str, str] = {}


def _get_app_root() -> str:
    """返回应用根目录；打包模式取 EXE 目录，开发模式取项目根目录。"""
    import sys

    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    else:
        return os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )


def _find_csv_path() -> str:
    """按多个兼容位置查找卡牌 CSV 文件。"""
    import sys

    app_root = _get_app_root()

    possible_paths = [
        os.path.join(app_root, "quanka", "SV_WB_Cards", "SV_WB_Cards.csv"),
        os.path.join(app_root, "SV_WB_Cards.csv"),
        os.path.join(
            os.path.dirname(app_root),
            "quanka",
            "SV_WB_Cards",
            "SV_WB_Cards.csv",
        ),
    ]

    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(os.path.abspath(sys.executable))
        possible_paths.extend(
            [
                os.path.join(
                    exe_dir,
                    "quanka",
                    "SV_WB_Cards",
                    "SV_WB_Cards.csv",
                ),
                os.path.join(exe_dir, "SV_WB_Cards.csv"),
            ]
        )

    for path in possible_paths:
        if os.path.exists(path):
            return os.path.abspath(path)

    return possible_paths[0]


def _load_card_id_map() -> Dict[str, str]:
    """从 CSV 加载卡牌 ID 到名称的映射。"""
    if _CARD_ID_MAP:
        return _CARD_ID_MAP

    csv_path = _find_csv_path()

    if not os.path.exists(csv_path):
        return {}

    try:
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                card_id = row.get("card_id", "").strip()
                card_name = row.get("name", "").strip()
                if card_id and card_name:
                    _CARD_ID_MAP[card_id] = card_name
    except Exception:
        pass

    return _CARD_ID_MAP


def get_card_name_by_id(card_id: str) -> Optional[str]:
    """通过 CSV 映射按卡牌 ID 查询名称。"""
    return _load_card_id_map().get(str(card_id).strip())


def _basename_stem(raw: str) -> str:
    s = str(raw or "").strip()
    if not s:
        return ""
    s = s.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    if "." in s:
        s = s.rsplit(".", 1)[0]
    return str(s or "")


def is_evo_card_name(card_name: str) -> bool:
    """判断名称、主文件名或完整文件名是否以 ``_evo`` 结尾。"""

    stem = _basename_stem(card_name)
    if not stem:
        return False
    return stem.lower().endswith("_evo")


def strip_evo_suffix(card_name: str) -> str:
    """移除卡名或主文件名末尾的 ``_evo``。"""

    raw = str(card_name or "").strip()
    if not raw:
        return ""
    if raw.lower().endswith("_evo"):
        return raw[:-4]
    return raw


def parse_follower_stat_suffix(card_name: str) -> Tuple[str, Optional[int], Optional[int]]:
    """从卡名末尾解析随从身材后缀。

    预期格式为 ``..._<atk>_<hp>``，从最右侧两个下划线段开始解析。成功时返回
    不带身材的基础名称、攻击和生命；失败时保留原名，攻击与生命返回 ``None``。
    """

    raw = str(card_name or "").strip()
    if not raw:
        return "", None, None

    parts = raw.split("_")
    if len(parts) < 3:
        return raw, None, None

    atk_s = parts[-2]
    hp_s = parts[-1]
    if not (atk_s.isdigit() and hp_s.isdigit()):
        return raw, None, None

    base_name = "_".join(parts[:-2]).strip()
    if not base_name:
        return raw, None, None

    try:
        return base_name, int(atk_s), int(hp_s)
    except Exception:
        return raw, None, None


def normalize_card_base_name(card_name: str) -> str:
    """返回供界面和配置键使用的稳定基础卡名。

    存在时移除随从身材后缀 ``_<atk>_<hp>`` 与进化图片后缀 ``_evo``；无后缀时
    保留原文本。
    """

    raw = str(card_name or "").strip()
    if not raw:
        return ""

    no_evo = strip_evo_suffix(raw)
    base, _atk, _hp = parse_follower_stat_suffix(no_evo)
    normalized = str(base or no_evo)
    return strip_evo_suffix(normalized)


def normalize_config_key(key: str) -> str:
    """将策略或配置键规范为无图片后缀的基础名称，同时支持 ``name@cost``。"""

    raw = str(key or "").strip()
    if not raw:
        return ""

    base, enhance = split_enhance_key(raw)
    normalized_base = normalize_card_base_name(str(base or ""))
    if enhance is None:
        return normalized_base
    return make_enhance_key(normalized_base, int(enhance))


def parse_card_stem(stem: str) -> Tuple[int, List[int], str]:
    """解析不带扩展名的卡牌文件名，返回基础费用、爆能费用列表与卡名。"""

    stem = str(stem or "").strip()
    if not stem:
        return 0, [], ""

    # 新格式形如 ``2@4@6_xxx``；先按下划线分离费用段与名称段。
    parts = stem.split("_")
    if not parts:
        return 0, [], stem

    # 费用段可能包含以 ``@`` 分隔的多个爆能层级。
    cost_part = parts[0]
    cost_segments = cost_part.split("@")

    try:
        base_cost = int(cost_segments[0])
    except Exception:
        # 基础费用无法解析时，将整个主文件名视为卡名。
        return 0, [], stem

    # 解析 ``@`` 分隔的爆能层级。
    enhance_raw: List[int] = []
    for seg in cost_segments[1:]:
        try:
            enhance_raw.append(int(seg))
        except Exception:
            break

    # 其余部分为卡名，同时兼容 ``4_6_name``、``4_6_8_name`` 旧格式。为避免把
    # ``4_10001110`` 这类数字卡牌 ID 误判为爆能层级，仅在后方仍有名称段时消费数字。
    name_start = 1
    if len(cost_segments) == 1:
        for idx in range(1, len(parts) - 1):
            seg = parts[idx]
            try:
                if seg.isdigit() and len(seg) == 8:
                    break
                enhance_raw.append(int(seg))
                name_start = idx + 1
                continue
            except Exception:
                break

    name_parts = parts[name_start:]

    card_name = "_".join([p for p in name_parts if p is not None])
    if not card_name:
        # 名称缺失时尽力回退到主文件名尾部。
        card_name = stem.split("_", 1)[-1] if "_" in stem else stem

    # 名称形似卡牌 ID 时，尝试通过 CSV 还原真实卡名。
    resolved_name = _resolve_card_name(card_name)
    if resolved_name:
        card_name = resolved_name

    # 爆能层级保序规范为：去重、大于基础费用、升序排列。
    enhance_costs: List[int] = []
    for c in enhance_raw:
        try:
            c = int(c)
        except Exception:
            continue
        if c <= base_cost:
            continue
        if c not in enhance_costs:
            enhance_costs.append(c)
    enhance_costs.sort()

    return int(base_cost), enhance_costs, str(card_name)


def _resolve_card_name(card_name: str) -> Optional[str]:
    """当名称形似卡牌 ID 时，通过 CSV 解析真实卡名。

    卡牌 ID 通常为 8 位数字；同时支持 ``10001110@1`` 异画形式，异画条目不存在时
    回退到基础卡牌 ID。
    """
    card_name = str(card_name or "").strip()
    if not card_name:
        return None

    # 进化模板会在 ID 后追加 ``_evo``；先解析基础 ID，再保留后缀，使下游可将
    # 基础图和进化图归到同一卡名。
    if card_name.lower().endswith("_evo"):
        resolved_base = _resolve_card_name(card_name[:-4])
        return f"{resolved_base}_evo" if resolved_base else None

    # 处理纯 8 位数字卡牌 ID。
    if card_name.isdigit() and len(card_name) == 8:
        return get_card_name_by_id(card_name)

    # 处理 ``10001110@1`` 异画格式。
    alt_art_pattern = re.match(r"^(\d{8})@(\d+)$", card_name)
    if alt_art_pattern:
        # 优先查询异画条目。
        resolved = get_card_name_by_id(card_name)
        if resolved:
            return resolved
        # 异画条目不存在时回退到基础 ID。
        base_id = alt_art_pattern.group(1)
        return get_card_name_by_id(base_id)

    # 对 ``10001110_2_2`` 等身材后缀形式，先移除后缀取得基础 ID。
    parts = card_name.split("_")
    if len(parts) >= 3 and parts[-1].isdigit() and parts[-2].isdigit():
        potential_id = "_".join(parts[:-2])
        if potential_id.isdigit() and len(potential_id) == 8:
            return get_card_name_by_id(potential_id)

        # 同时支持带身材后缀的异画格式，例如 ``10001110@1_2_3``。
        alt_art_pattern = re.match(r"^(\d{8})@(\d+)$", potential_id)
        if alt_art_pattern:
            # 优先查询异画条目。
            resolved = get_card_name_by_id(potential_id)
            if resolved:
                return resolved
            # 异画条目不存在时回退到基础 ID。
            base_id = alt_art_pattern.group(1)
            return get_card_name_by_id(base_id)

    return None


def parse_card_filename(filename: str) -> Tuple[int, List[int], str]:
    """解析带扩展名的卡牌图片文件名。"""

    name = str(filename or "")
    stem = name.rsplit(".", 1)[0]
    return parse_card_stem(stem)


def make_enhance_key(card_name: str, enhance_cost: int) -> str:
    """为爆能层级变体构造配置键。"""

    return f"{str(card_name)}@{int(enhance_cost)}"


def split_enhance_key(key: str) -> Tuple[str, Optional[int]]:
    """将配置键拆分为基础名称和爆能费用。"""

    s = str(key or "")
    if "@" not in s:
        return s, None
    base, tail = s.rsplit("@", 1)
    try:
        return base, int(tail)
    except Exception:
        return s, None
