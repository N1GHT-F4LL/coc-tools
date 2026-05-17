from .base_screen import BaseScreen

class HomeScreen(BaseScreen):
    def is_current_screen(self):
        # Màn hình chính nhận diện bằng nút Attack
        return self.ui_manager.wait_until_appears("icon_attack", timeout=2) is not None

    def collect_resources(self):
        print("Collecting resources...")
        # Tìm và click mỏ vàng/elixir
        self.ui_manager.click_if_exists("icon_gold_mine_full")
        self.ui_manager.click_if_exists("icon_elixir_collector_full")
        self.ui_manager.click_if_exists("icon_dark_elixir_drill_full")
