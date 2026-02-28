# StrategyProfile / effects schema (Step2B draft)

本文件描述 Step2B 引入的最小 `strategy.effects` 配置结构（先覆盖现有模式选项/特殊目标/进化后特殊点击），用于逐步替换散落在代码中的硬编码 dict。

## 位置

`config.json` 顶层：

```json
{
  "strategy": {
    "effects": {
      "卡名": {
        "on_play": [{"select_option": 2}],
        "on_evolve": [{"action": "attack_enemy_follower_hp_less_than_4"}],
        "on_super_evolve": [{"select_option": 1}]
      }
    }
  }
}
```

## triggers

- `on_play`: 出牌后需要额外交互（模式选项/选目标等）
- `on_evolve`: 普通进化后需要额外交互
- `on_super_evolve`: 超进化后需要额外交互

## steps（当前最小支持）

每个 trigger 对应一个 step 列表（按顺序执行）。目前为了兼容旧逻辑，优先支持以下字段：

1) `select_option`: `1 | 2`

- 对应 UI 中“模式选项/进化选项”的二选一。
- 现阶段仍使用旧坐标点击（选项1/选项2），不在这里抽象坐标。

2) `target_type`: `str`

- 兼容旧 `SPECIAL_CARDS` 的 `target_type`（例如 `enemy_player` / `shield_or_highest_hp` 等）。
- 现阶段执行仍走旧 handler；后续会升级为 `TargetSpec` + selector DSL。

3) `action`: `str`

- 兼容旧 `EVOLVE_SPECIAL_ACTIONS` 的 action（例如 `attack_enemy_follower_hp_less_than_4`）。

## 向后兼容

- 旧字段 `card_mode_options` / `card_evolve_mode_options` 仍保留读取。
- Step2B S2.4 会通过 migration 将旧字段写入 `strategy.effects`（并将默认特殊卡/进化特殊动作 seed 到该结构）。
