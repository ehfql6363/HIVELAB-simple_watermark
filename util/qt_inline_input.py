# qt_inline_input.py
import sys, json, argparse, os
from PySide6 import QtCore, QtGui, QtWidgets

def jprint(obj):
    print(json.dumps(obj, ensure_ascii=False), flush=True)

class Edit(QtWidgets.QLineEdit):
    preeditChanged = QtCore.Signal(str)  # 편하게 쓰려고 사용자 시그널

    def inputMethodEvent(self, e: QtGui.QInputMethodEvent):  # preedit 포착
        super().inputMethodEvent(e)
        pre = e.preeditString() or ""
        self.preeditChanged.emit(pre)

class InlineWin(QtWidgets.QWidget):
    def __init__(self, x, y, w, h, text0, kwfile=None):
        super().__init__(None, QtCore.Qt.Window | QtCore.Qt.FramelessWindowHint)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground, False)
        self.setGeometry(x, y, w, h)

        lay = QtWidgets.QVBoxLayout(self); lay.setContentsMargins(0,0,0,0)
        self.edit = Edit(self); self.edit.setText(text0 or "")
        lay.addWidget(self.edit)

        # 폰트/여백 조금 보정 (선택)
        f = self.edit.font(); f.setPointSizeF(f.pointSizeF()+0.0); self.edit.setFont(f)
        self.edit.setFocusPolicy(QtCore.Qt.StrongFocus)

        # 이벤트 연결
        self.edit.textChanged.connect(self.on_change)
        self.edit.editingFinished.connect(self.on_finish)
        self.edit.preeditChanged.connect(self.on_preedit)

        # 키 처리: Esc → cancel
        self.edit.installEventFilter(self)

        self.show(); self.raise_(); self.activateWindow()
        self.edit.setFocus(QtCore.Qt.OtherFocusReason)
        self.edit.end(False)

        # HWND 알림
        try:
            hwnd = int(self.winId())
        except Exception:
            hwnd = 0
        jprint({"event": "ready", "hwnd": hwnd})

        # 키워드 파일(자동완성용)이 필요하면 여기서 읽어다가 사용 가능
        self.kw = []
        if kwfile and os.path.exists(kwfile):
            try:
                import json as _json
                with open(kwfile, "r", encoding="utf-8") as f:
                    self.kw = _json.load(f)
            except Exception:
                pass

    def eventFilter(self, obj, ev):
        if obj is self.edit and ev.type() == QtCore.QEvent.KeyPress:
            if ev.key() == QtCore.Qt.Key_Escape:
                jprint({"event":"cancel"})
                QtWidgets.QApplication.quit()
                return True
        return super().eventFilter(obj, ev)

    def on_preedit(self, pre):
        jprint({"event":"preedit", "preedit": pre})

    def on_change(self, s):
        jprint({"event":"change", "text": s})

    def on_finish(self):
        # editingFinished는 focus-out/Enter에서 발생
        s = self.edit.text()
        jprint({"event":"finish", "text": s})
        QtWidgets.QApplication.quit()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--x", type=int, required=True)
    ap.add_argument("--y", type=int, required=True)
    ap.add_argument("--w", type=int, required=True)
    ap.add_argument("--h", type=int, required=True)
    ap.add_argument("--text", type=str, default="")
    ap.add_argument("--kwfile", type=str, default="")
    a = ap.parse_args()

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    w = InlineWin(a.x, a.y, a.w, a.h, a.text, a.kwfile)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
