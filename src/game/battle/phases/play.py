"""Play phase wrapper."""

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
        ds.sleep(0.5)

        # 点击空白处关闭面板
        self.actions._click_blank_panel(sleep_seconds=0.5)
        return bool(ok)
