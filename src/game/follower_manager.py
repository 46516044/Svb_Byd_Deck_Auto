from __future__ import annotations

import time
from typing import List, Optional, Tuple


class FollowerManager:
    """随从管理器，用于管理我方和敌方随从的位置信息"""
    
    def __init__(self):
        # (x, y, type, name)
        self.positions: List[Tuple[int, int, str, Optional[str]]] = []
        self.enemy_positions: List[Tuple[int, int, str, Optional[str]]] = []

        self.last_updated_ts: float = 0.0
        self.last_enemy_updated_ts: float = 0.0
    
    def update_positions(self, positions: List[Tuple[int, int, str, Optional[str]]]):
        """更新我方随从位置"""
        self.positions = positions
        self.last_updated_ts = time.time()
    
    def get_positions(self) -> List[Tuple[int, int, str, Optional[str]]]:
        """获取我方随从位置"""
        return self.positions

    def get_positions_sorted(self, *, sort_desc: bool = False) -> List[Tuple[int, int, str, Optional[str]]]:
        """按x坐标排序返回（不修改内部存储顺序）。"""

        return sorted(self.positions or [], key=lambda p: int(p[0]), reverse=bool(sort_desc))

    def age_seconds(self) -> float:
        """我方随从数据距上次更新的秒数（未更新过返回inf）。"""

        if not self.last_updated_ts:
            return float("inf")
        return max(0.0, time.time() - float(self.last_updated_ts))

    def is_fresh(self, *, max_age_seconds: float) -> bool:
        """是否认为当前我方随从缓存仍然新鲜可用。"""

        try:
            max_age = float(max_age_seconds)
        except Exception:
            max_age = 0.0
        return bool(self.positions) and self.age_seconds() <= max(0.0, max_age)
    
    def get_count(self) -> int:
        """获取我方随从数量"""
        return len(self.positions)
    
    def get_by_type(self, follower_type: str) -> List[Tuple[int, int]]:
        """根据类型获取随从位置"""
        return [(x, y) for x, y, ftype, _ in self.positions if ftype == follower_type]
    
    def update_enemy_positions(self, enemy_positions: List[Tuple[int, int, str, Optional[str]]]):
        """更新敌方随从位置"""
        self.enemy_positions = enemy_positions
        self.last_enemy_updated_ts = time.time()
    
    def get_enemy_positions(self) -> List[Tuple[int, int, str, Optional[str]]]:
        """获取敌方随从位置"""
        return self.enemy_positions 
