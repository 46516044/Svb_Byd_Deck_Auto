# strategy.effects schema (Step3A ops)

本文件描述 Step3A 引入的 `strategy.effects` 配置结构：以 `OperationSpec` 为核心，把 Trigger 与 Operation 解耦。

## 位置

`config.json` 顶层：

```json
{
  "strategy": {
    "effects": {
      "卡名": {
        "on_play": [
          {"op": "select_option", "index": 2},
          {
            "op": "select_targets",
            "target": {"kind": "enemy_follower", "selector": "hp_leq", "params": {"max_hp": 3}},
            "count": 1,
            "distinct_xy": true,
            "is_select_ui": true
          }
        ],
        "on_evolve": [
          {"op": "legacy_action", "action": "attack_enemy_follower_hp_less_than_4"}
        ],
        "on_super_evolve": [
          {"op": "select_option", "index": 1}
        ],
        "on_attack": []
      }
    }
  }
}
```

## card_key 规则

- `on_play`（手牌触发）支持爆能 key：`卡名@6`。
- `on_evolve/on_super_evolve/on_attack`（随从触发）默认按随从基础名（不带 @）查找。

## triggers

- `on_play`: 出牌时的额外交互
- `on_attack`: 随从攻击后的额外交互
- `on_evolve`: 普通进化后的额外交互
- `on_super_evolve`: 超进化后的额外交互

## steps = OperationSpec[]

每个 trigger 对应一个 step 列表（按顺序执行），每个 step 是一个 dict：

```json
{"op": "<operation_id>", "...params"}
```

当前内置/最小可用 ops：

- `select_option`: 二选一（`index: 1|2`）
- `select_targets`: 统一目标选择（`target/count/distinct_xy/is_select_ui`）
- `cancel_action`: 点空白取消/关闭面板

迁移期兼容 ops（保留旧逻辑入口）：

- `legacy_target_type`: 兼容旧 `target_type`
- `legacy_action`: 兼容旧 `action`

## TargetSpec（select_targets.target）

```json
{"kind": "enemy_follower", "selector": "highest_hp", "params": {}}
```

当前最小支持：

- `enemy_leader`
- `enemy_follower.highest_hp`
- `enemy_follower.hp_leq(max_hp)`
- `enemy_follower.ward_or_highest_hp`
- `friendly_follower.by_evolve_priority(exclude_self)`

## 向后兼容

- 旧 step 结构（`{"select_option":1}` / `{"target_type":"..."}` / `{"action":"..."}`）会被 migration 自动升级为 op。
- 旧顶层字段 `card_mode_options` / `card_evolve_mode_options` 仍保留读取，但 UI 不再写入；优先使用 `strategy.effects`。
