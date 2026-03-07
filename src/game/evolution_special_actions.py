"""
进化/超进化特殊操作处理模块
处理进化/超进化后的特殊action（如铁拳神父等）
"""

from src.game.policy.effects import get_card_effect_steps

from src.config.strategy_effects import normalize_effect_steps_to_ops
from src.game.effects import EffectEngine, FollowerContext

class EvolutionSpecialActions:
    """进化/超进化特殊操作处理类"""
    
    def __init__(self, device_state):
        self.device_state = device_state
    
    def handle_evolve_special_action(self, follower_name, pos=None, is_super_evolution=False, existing_followers=None):
        """
        处理进化/超进化后特殊action（如铁拳神父等），便于扩展
        follower_name: 卡牌名称
        pos: 进化随从的坐标（如有需要）
        is_super_evolution: 是否为超进化
        existing_followers: 已扫描的随从结果，避免重复扫描
        """
        trigger = "on_super_evolve" if is_super_evolution else "on_evolve"

        effect_key = str(follower_name or "")
        try:
            runtime = getattr(self.device_state, "battle_runtime_state", None)
            if runtime is not None and hasattr(runtime, "get_effect_key_for_ours"):
                key = runtime.get_effect_key_for_ours(
                    follower_pos=pos,
                    fallback_name=str(follower_name or ""),
                )
                if key:
                    effect_key = str(key)
        except Exception:
            effect_key = str(follower_name or "")

        steps = get_card_effect_steps(
            getattr(self.device_state, "config", None), card_name=effect_key, trigger=trigger
        )

        ops = normalize_effect_steps_to_ops(steps)

        # Preserve legacy runtime semantics: evolve special clicks before select_option.
        ops = [
            o for o in ops if isinstance(o, dict) and str(o.get("op") or "") != "select_option"
        ] + [
            o for o in ops if isinstance(o, dict) and str(o.get("op") or "") == "select_option"
        ]

        ctx = FollowerContext(
            device_state=self.device_state,
            follower_name=str(effect_key or follower_name or ""),
            follower_pos=(int(pos[0]), int(pos[1])) if isinstance(pos, (list, tuple)) and len(pos) >= 2 else None,
            is_super_evolution=bool(is_super_evolution),
            existing_followers=existing_followers,
        )
        EffectEngine.run_ops(ops, ctx=ctx, trigger_id=trigger)
