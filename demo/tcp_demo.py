"""Live demo: TCP Reno vs CUBIC vs BBR chạy thời gian thực trên cùng điều kiện mạng.

Chạy:   python tcp_demo.py
Phím tắt:  L = mất gói (3 dupACK)   T = timeout (RTO)   Space = tạm dừng   R = reset
"""
import sys
from collections import deque

import numpy as np
import pyqtgraph as pg
from PySide6 import QtCore, QtGui, QtWidgets

from tcp_sim import BBR, Cubic, Env, Flow, Reno

DT = 0.001                 # bước mô phỏng (s)
FRAME_MS = 33              # chu kỳ vẽ (ms thực)
SAMPLE_EVERY = 10          # lấy mẫu vẽ mỗi 10 bước = 10 ms mô phỏng
WINDOW = 30.0              # độ rộng trục thời gian hiển thị (s)
ALGOS = (Reno, Cubic, BBR)
SPEEDS = (0.25, 0.5, 1, 2, 4)

PRESETS = {
    "Mặc định": dict(bw=20, rtt=60, buf=100, loss=0.0),
    "Đường dài (RTT 200 ms)": dict(bw=20, rtt=200, buf=100, loss=0.0),
    "Wi-Fi nhiễu (mất 1%)": dict(bw=20, rtt=60, buf=100, loss=1.0),
    "Bufferbloat (buffer 400)": dict(bw=20, rtt=60, buf=400, loss=0.0),
    "Buffer nông (10 gói)": dict(bw=20, rtt=60, buf=10, loss=0.0),
}

# Tham số tĩnh của từng thuật toán (hiển thị cố định)
STATIC = {
    Reno: "AI: <b>+1 MSS/RTT</b> · MD: <b>cwnd × 0.5</b><br>"
          "Slow start: ×2 mỗi RTT · RTO: cwnd = 1",
    Cubic: "W(t) = <b>C(t − K)³ + W<sub>max</sub></b><br>"
           "C = <b>0.4</b> · β = <b>0.7</b> · K = ∛(W<sub>max</sub>(1−β)/C)",
    BBR: "pacing = <b>gain × BtlBw</b> · cwnd = <b>2 × BDP</b><br>"
         "gain 1.25 → 0.75 → 1×6 · PROBE_RTT mỗi 10 s",
}

STYLE = """
QWidget { font-size: 13px; color: #0f172a; }
QMainWindow, #root { background: #f8fafc; }
QGroupBox { background: white; border: 1px solid #e2e8f0; border-radius: 10px;
            margin-top: 14px; padding: 10px 10px 6px 10px; font-weight: 600; }
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 4px; color: #475569; }
QPushButton { background: white; border: 1px solid #cbd5e1; border-radius: 8px;
              padding: 7px 12px; font-weight: 600; }
QPushButton:hover { background: #f1f5f9; }
QPushButton#danger { background: #dc2626; color: white; border: none; }
QPushButton#danger:hover { background: #b91c1c; }
QPushButton#warn { background: #f59e0b; color: white; border: none; }
QPushButton#warn:hover { background: #d97706; }
QSlider::groove:horizontal { height: 6px; background: #e2e8f0; border-radius: 3px; }
QSlider::sub-page:horizontal { background: #334155; border-radius: 3px; }
QSlider::handle:horizontal { background: white; border: 2px solid #334155; width: 14px;
                             margin: -6px 0; border-radius: 8px; }
QLabel#info { background: white; border: 1px solid #e2e8f0; border-radius: 10px; padding: 8px;
              font-size: 12px; }
QLabel#status { color: #475569; padding: 2px 4px; }
"""


class Slider(QtWidgets.QWidget):
    """Thanh trượt có nhãn; giá trị thực = giá trị nguyên × scale."""
    changed = QtCore.Signal(float)

    def __init__(self, title, lo, hi, value, scale=1.0, fmt="{:.0f}"):
        super().__init__()
        self.scale, self.fmt = scale, fmt
        self.title = QtWidgets.QLabel(title)
        self.value_lbl = QtWidgets.QLabel()
        self.value_lbl.setMinimumWidth(80)
        self.value_lbl.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        self.value_lbl.setStyleSheet("font-weight: 700;")
        self.slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.slider.setRange(int(round(lo / scale)), int(round(hi / scale)))
        self.slider.valueChanged.connect(self._on_change)
        grid = QtWidgets.QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.addWidget(self.title, 0, 0)
        grid.addWidget(self.value_lbl, 0, 1)
        grid.addWidget(self.slider, 1, 0, 1, 2)
        self.set(value)

    def value(self):
        return self.slider.value() * self.scale

    def set(self, v):
        self.slider.setValue(int(round(v / self.scale)))
        self._on_change()

    def _on_change(self, *_):
        self.value_lbl.setText(self.fmt.format(self.value()))
        self.changed.emit(self.value())


class AlgoRow:
    """Một đồ thị + bảng thông tin cho một thuật toán."""

    def __init__(self, cls):
        self.cls = cls
        self.plot = pg.PlotWidget()
        p = self.plot
        p.setBackground("w")
        p.showGrid(x=True, y=True, alpha=0.15)
        p.setMenuEnabled(False)
        p.setMouseEnabled(x=False, y=False)
        p.hideButtons()
        p.setLabel("left", f"<b>{cls.name}</b> — gói", color=cls.color)
        p.addLegend(offset=(-10, 8), labelTextSize="9pt", brush=pg.mkBrush(255, 255, 255, 200))
        c = QtGui.QColor(cls.color)
        faint = QtGui.QColor(c)
        faint.setAlpha(140)
        self.bdp_line = pg.InfiniteLine(angle=0, pen=pg.mkPen("#64748b", width=1.2, style=QtCore.Qt.DashLine),
                                        label="BDP", labelOpts=dict(position=0.15, color="#64748b"))
        self.thr_line = pg.InfiniteLine(angle=0, pen=pg.mkPen("#dc2626", width=1.2, style=QtCore.Qt.DotLine),
                                        label="BDP + buffer", labelOpts=dict(position=0.05, color="#dc2626"))
        p.addItem(self.bdp_line)
        p.addItem(self.thr_line)
        self.cwnd_curve = p.plot(pen=pg.mkPen(faint, width=1.3, style=QtCore.Qt.DashLine), name="cwnd")
        self.infl_curve = p.plot(pen=pg.mkPen(c, width=2.4), name="dữ liệu đang bay")
        self.loss_pts = pg.ScatterPlotItem(symbol="x", size=11, pen=pg.mkPen("#dc2626", width=2.2),
                                           brush=None, name="mất gói")
        p.addItem(self.loss_pts)

        self.info = QtWidgets.QLabel()
        self.info.setObjectName("info")
        self.info.setTextFormat(QtCore.Qt.RichText)
        self.info.setFixedWidth(360)
        self.info.setAlignment(QtCore.Qt.AlignTop | QtCore.Qt.AlignLeft)
        self.reset()

    def reset(self):
        n = int(WINDOW / (DT * SAMPLE_EVERY)) + 5
        self.t, self.infl, self.cwnd = deque(maxlen=n), deque(maxlen=n), deque(maxlen=n)

    def record(self, flow):
        self.t.append(flow.now)
        self.infl.append(flow.inflight)
        self.cwnd.append(flow.cc.cwnd)

    def redraw(self, flow):
        t = np.fromiter(self.t, float)
        self.infl_curve.setData(t, np.fromiter(self.infl, float))
        self.cwnd_curve.setData(t, np.fromiter(self.cwnd, float))
        lo = flow.now - WINDOW
        while flow.loss_marks and flow.loss_marks[0][0] < lo:
            flow.loss_marks.popleft()
        if flow.loss_marks:
            lt, ly = zip(*flow.loss_marks)
            self.loss_pts.setData(lt, ly)
        else:
            self.loss_pts.clear()

    def update_info(self, flow, env):
        tput = flow.throughput_mbps()
        algo = list(flow.cc.info().items())
        state = algo.pop(0)[1]                  # mục đầu tiên là trạng thái / vùng
        cells = [("Throughput", f"{tput:.1f} Mbps"),
                 ("Tận dụng", f"{min(100, tput / env.bw_mbps * 100):.0f} %"),
                 ("RTT", f"{flow.rtt * 1000:.0f} ms"),
                 ("Hàng đợi", f"{flow.q:.0f}/{env.buffer_pkts:.0f}"),
                 ("Mất gói", f"{flow.loss_events} lần")] + algo
        cell = "<td style='color:#64748b;padding-right:6px'>{}</td><td style='font-weight:700;padding-right:14px'>{}</td>"
        rows = "".join("<tr>" + "".join(cell.format(k, v) for k, v in cells[i:i + 2]) + "</tr>"
                       for i in range(0, len(cells), 2))
        self.info.setText(
            f"<span style='color:{self.cls.color};font-weight:700;font-size:14px'>{self.cls.name}</span>"
            f" &nbsp;<span style='background:{self.cls.color};color:white;font-weight:600'>&nbsp;{state}&nbsp;</span>"
            f"<div style='color:#334155;margin:3px 0 6px 0'>{STATIC[self.cls]}</div>"
            f"<table cellspacing='0' cellpadding='1'>{rows}</table>")


class Demo(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("TCP Congestion Control — Reno · CUBIC · BBR")
        self.env = Env()
        self.paused = False
        self.speed = 1.0
        self.ticks = 0
        self.frames = 0

        root = QtWidgets.QWidget(objectName="root")
        self.setCentralWidget(root)
        vbox = QtWidgets.QVBoxLayout(root)
        vbox.setContentsMargins(12, 6, 12, 8)
        vbox.addLayout(self._build_controls())

        grid = QtWidgets.QGridLayout()
        grid.setSpacing(8)
        self.rows = [AlgoRow(cls) for cls in ALGOS]
        for i, row in enumerate(self.rows):
            grid.addWidget(row.plot, i, 0)
            grid.addWidget(row.info, i, 1)
            if i:
                row.plot.setXLink(self.rows[0].plot)
        self.rows[-1].plot.setLabel("bottom", "thời gian (s)")
        vbox.addLayout(grid, 1)

        self.status = QtWidgets.QLabel(objectName="status")
        vbox.addWidget(self.status)

        for key, fn in (("L", self.inject_loss), ("T", self.inject_rto),
                        ("Space", self.toggle_pause), ("R", self.reset)):
            QtGui.QShortcut(QtGui.QKeySequence(key), self, activated=fn)

        self.reset()
        self.timer = QtCore.QTimer(self, interval=FRAME_MS, timeout=self.tick)
        self.timer.start()

    # ------------------------------------------------------------ giao diện
    def _build_controls(self):
        env_box = QtWidgets.QGroupBox("Môi trường mạng (áp dụng ngay)")
        eg = QtWidgets.QGridLayout(env_box)
        eg.setHorizontalSpacing(24)
        self.s_bw = Slider("Băng thông nút cổ chai", 5, 100, self.env.bw_mbps, 1, "{:.0f} Mbps")
        self.s_rtt = Slider("RTT cơ sở (ping)", 10, 300, self.env.rtt_ms, 5, "{:.0f} ms")
        self.s_buf = Slider("Buffer router", 5, 400, self.env.buffer_pkts, 5, "{:.0f} gói")
        self.s_loss = Slider("Mất gói ngẫu nhiên", 0, 5, self.env.loss_pct, 0.1, "{:.1f} %")
        self.s_bw.changed.connect(lambda v: setattr(self.env, "bw_mbps", v))
        self.s_rtt.changed.connect(lambda v: setattr(self.env, "rtt_ms", v))
        self.s_buf.changed.connect(lambda v: setattr(self.env, "buffer_pkts", v))
        self.s_loss.changed.connect(lambda v: setattr(self.env, "loss_pct", v))
        for i, s in enumerate((self.s_bw, self.s_rtt, self.s_buf, self.s_loss)):
            eg.addWidget(s, 0, i)

        ev_box = QtWidgets.QGroupBox("Sự kiện")
        eh = QtWidgets.QHBoxLayout(ev_box)
        b_loss = QtWidgets.QPushButton("Mất gói  [L]", objectName="danger")
        b_loss.setToolTip("Làm rơi 3 gói đang bay → phát hiện bằng 3 dupACK sau ~1 RTT")
        b_rto = QtWidgets.QPushButton("Timeout RTO  [T]", objectName="warn")
        b_rto.setToolTip("Mất toàn bộ gói đang bay (đứt link tạm thời) → chờ hết RTO")
        self.b_pause = QtWidgets.QPushButton("Tạm dừng  [Space]")
        b_reset = QtWidgets.QPushButton("Reset  [R]")
        b_loss.clicked.connect(self.inject_loss)
        b_rto.clicked.connect(self.inject_rto)
        self.b_pause.clicked.connect(self.toggle_pause)
        b_reset.clicked.connect(self.reset)
        for b in (b_loss, b_rto, self.b_pause, b_reset):
            eh.addWidget(b)

        misc_box = QtWidgets.QGroupBox("Kịch bản · tốc độ")
        mg = QtWidgets.QGridLayout(misc_box)
        self.preset = QtWidgets.QComboBox()
        self.preset.addItems(PRESETS)
        self.preset.activated.connect(lambda _: self.apply_preset(self.preset.currentText()))
        self.s_speed = Slider("Tốc độ mô phỏng", 0, len(SPEEDS) - 1, SPEEDS.index(1), 1, "")
        self.s_speed.changed.connect(self._on_speed)
        self._on_speed(self.s_speed.value())
        mg.addWidget(self.preset, 0, 0)
        mg.addWidget(self.s_speed, 1, 0)

        top = QtWidgets.QHBoxLayout()
        top.addWidget(env_box, 5)
        top.addWidget(ev_box, 3)
        top.addWidget(misc_box, 1)
        return top

    def _on_speed(self, v):
        self.speed = SPEEDS[int(v)]
        self.s_speed.value_lbl.setText(f"{self.speed:g}×")

    def apply_preset(self, name):
        p = PRESETS[name]
        self.s_bw.set(p["bw"])
        self.s_rtt.set(p["rtt"])
        self.s_buf.set(p["buf"])
        self.s_loss.set(p["loss"])

    # ------------------------------------------------------------- điều khiển
    def reset(self):
        self.flows = [Flow(cls(), self.env, seed=i + 1) for i, cls in enumerate(ALGOS)]
        for row in self.rows:
            row.reset()
        self.ticks = 0

    def inject_loss(self):
        for f in self.flows:
            f.inject_loss(3)

    def inject_rto(self):
        for f in self.flows:
            f.inject_rto()

    def toggle_pause(self):
        self.paused = not self.paused
        self.b_pause.setText("Tiếp tục  [Space]" if self.paused else "Tạm dừng  [Space]")

    # --------------------------------------------------------------- vòng lặp
    def tick(self):
        if not self.paused:
            for _ in range(int(round(self.speed * FRAME_MS / 1000 / DT))):
                self.ticks += 1
                for f in self.flows:
                    f.step(DT)
                if self.ticks % SAMPLE_EVERY == 0:
                    for row, f in zip(self.rows, self.flows):
                        row.record(f)
        self.redraw()

    def redraw(self):
        self.frames += 1
        env, now = self.env, self.flows[0].now
        thr = env.bdp + env.buffer_pkts
        ymax = thr * 1.25
        for row, f in zip(self.rows, self.flows):
            row.redraw(f)
            if row.infl:
                ymax = max(ymax, max(row.infl) * 1.05)
        for row, f in zip(self.rows, self.flows):
            row.bdp_line.setValue(env.bdp)
            row.thr_line.setValue(thr)
            row.plot.setYRange(0, ymax, padding=0)
            if self.frames % 3 == 0:
                row.update_info(f, env)
        self.rows[0].plot.setXRange(max(0.0, now - WINDOW), max(WINDOW, now), padding=0)
        state = "  ⏸ TẠM DỪNG" if self.paused else ""
        self.status.setText(
            f"t = {now:6.1f} s   │   C = {env.cap:.0f} gói/s   │   BDP = C × RTT = {env.bdp:.0f} gói   │   "
            f"ngưỡng mất gói ≈ BDP + buffer = {thr:.0f} gói   │   tốc độ {self.speed:g}×{state}")


def main():
    pg.setConfigOptions(antialias=True)
    app = QtWidgets.QApplication(sys.argv)
    app.setStyleSheet(STYLE)
    w = Demo()
    w.showMaximized()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
