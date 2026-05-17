class BaseScreen:
    def __init__(self, ui_manager):
        self.ui_manager = ui_manager

    def is_current_screen(self):
        raise NotImplementedError

    def close_popups(self):
        # Scan for generic close/okay buttons
        self.ui_manager.click_if_exists("btn_close")
        self.ui_manager.click_if_exists("btn_okay")
