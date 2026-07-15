"""出牌阶段包装器。"""

from __future__ import annotations


class PlayPhase:
    def __init__(self, actions):
        self.actions = actions

    def run(self, *, post_show_sleep: float) -> bool:
        ds = self.actions.device_state
        ds.logger.info("[Phase] play")

        # 展牌
        self.actions._show_cards_once()
        ds.sleep(float(post_show_sleep))

        # 截图并出牌
        image = self.actions._take_screenshot_bgr()
        if image is None:
            ds.logger.warning("无法获取截图，跳过出牌")
            return False

        ok = self.actions._play_cards(image)
    # 等待出牌后的召唤、效果和增益动画稳定，再进入进化或攻击扫描。下方空白区域
    # 点击还会等待 0.5 秒，因此出牌后的总稳定时间为 2 秒。
        ds.sleep(1.5)

        # 点击空白处关闭面板
        self.actions._click_blank_panel(sleep_seconds=0.5)
        return bool(ok)
