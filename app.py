# -*- coding: utf-8 -*-
"""
App entry — Phase 3 (UI 컴포넌트 분리)
"""
from __future__ import annotations

from controller import AppController
from ui.main_window import MainWindow

def main():
    controller = AppController()
    app = MainWindow(controller=controller)
    app.mainloop()

if __name__ == "__main__":
    main()
