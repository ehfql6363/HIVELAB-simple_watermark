# qt_inline_input.py
from __future__ import annotations
import sys, json, argparse
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QLineEdit

def jprint(obj):  # 줄단위 JSON 출력
    print(json.dumps(obj, ensure_ascii=False), flush=True)

class InlineEdit(QLineEdit):
    def __init__(self, initial: str):
        super().__init__(initial)
        # 무테 + 항상 위 + 툴 윈도우(작게)
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint | Qt.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.setFocusPolicy(Qt.StrongFocus)
        self.textEdited.connect(self._on_text_edited)

    def _on_text_edited(self, s: str):
        # 사용자 편집(커밋된 부분) 변경 즉시 알림
        jprint({"event": "change", "text": s})

    # IME 조합 중 문자열까지 전달
    def inputMethodEvent(self, e):  # type: ignore[override]
        super().inputMethodEvent(e)
        pre = e.preeditString()  # 조합 문자열
        visible = self.text() + pre  # 화면에 보이는 값(커밋+조합)
        jprint({"event": "preedit", "text": visible})

    def focusOutEvent(self, e):  # type: ignore[override]
        jprint({"event": "finish", "text": self.text()})
        super().focusOutEvent(e)
        QTimer.singleShot(0, QApplication.instance().quit)

    def keyPressEvent(self, e):  # type: ignore[override]
        if e.key() in (Qt.Key_Return, Qt.Key_Enter):
            jprint({"event": "finish", "text": self.text()})
            QTimer.singleShot(0, QApplication.instance().quit)
            return
        if e.key() == Qt.Key_Escape:
            jprint({"event": "cancel"})
            QTimer.singleShot(0, QApplication.instance().quit)
            return
        super().keyPressEvent(e)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--x", type=int, required=True)
    ap.add_argument("--y", type=int, required=True)
    ap.add_argument("--w", type=int, required=True)
    ap.add_argument("--h", type=int, required=True)
    ap.add_argument("--text", type=str, default="")
    args = ap.parse_args()

    app = QApplication(sys.argv)
    w = InlineEdit(args.text)
    # 약간의 내부 패딩 고려해서 살짝 키움(보기 좋게)
    w.setGeometry(args.x, args.y, max(args.w, 120), max(args.h, 28))
    w.show()
    w.setFocus(Qt.ActiveWindowFocusReason)
    # 커서 끝으로
    w.setCursorPosition(len(args.text or ""))
    app.exec()

if __name__ == "__main__":
    main()
