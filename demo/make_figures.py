"""Vẽ toàn bộ hình minh họa cho slide vào ../images.

Chạy:  python make_figures.py
Các đồ thị truyền tải dùng chính engine `tcp_sim` của live demo.
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Rectangle

from tcp_sim import BBR, Cubic, Env, Reno, run

OUT = Path(__file__).resolve().parent.parent / "images"
OUT.mkdir(exist_ok=True)

INK, MUTED, GRID, RED = "#0f172a", "#64748b", "#e2e8f0", "#dc2626"

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 12, "text.color": INK,
    "axes.edgecolor": MUTED, "axes.labelcolor": INK, "axes.titleweight": "bold",
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8,
    "xtick.color": MUTED, "ytick.color": MUTED, "legend.frameon": False,
    "savefig.dpi": 160, "savefig.bbox": "tight", "savefig.transparent": False,
})


def save(fig, name):
    fig.savefig(OUT / name, facecolor="white")
    plt.close(fig)
    print("✓", name)


# ------------------------------------------------------------------ khái niệm
def sliding_window():
    fig, ax = plt.subplots(figsize=(12, 2.9))
    ax.set_axis_off()
    groups = [(1, 5, "#cbd5e1", "Đã gửi & đã ACK"), (6, 11, "#3b82f6", "Đã gửi, chờ ACK (in-flight)"),
              (12, 15, "#bfdbfe", "Được phép gửi ngay"), (16, 20, "white", "Chưa được gửi")]
    for a, b, c, label in groups:
        for i in range(a, b + 1):
            ax.add_patch(Rectangle((i, 0), 0.92, 1, fc=c, ec=MUTED, lw=1))
            ax.text(i + 0.46, 0.5, str(i), ha="center", va="center", fontsize=12,
                    color="white" if c == "#3b82f6" else INK)
        ax.text((a + b + 0.92) / 2, -0.35, label, ha="center", va="top", fontsize=12, color=INK)
    ax.annotate("", xy=(5.95, 1.35), xytext=(15.97, 1.35),
                arrowprops=dict(arrowstyle="<->", color=INK, lw=1.6))
    ax.text(10.96, 1.5, "Cửa sổ gửi = min(cwnd, rwnd)", ha="center", va="bottom",
            fontsize=14, fontweight="bold")
    ax.annotate("ACK đến → cửa sổ trượt sang phải", xy=(17.2, 1.35), xytext=(16.4, 1.9),
                fontsize=12, color=MUTED, arrowprops=dict(arrowstyle="->", color=MUTED))
    ax.set_xlim(0.8, 21.2)
    ax.set_ylim(-0.9, 2.3)
    save(fig, "sliding_window.png")


def phases():
    """cwnd theo từng RTT: slow start → CA → 3 dupACK → timeout (Reno vs Tahoe)."""
    def trace(tahoe):
        cwnd, ss, out = 1.0, 32.0, []
        for r in range(46):
            out.append(cwnd)
            if r == 17:                                  # 3 dupACK
                ss = cwnd / 2
                cwnd = 1.0 if tahoe else ss
            elif r == 34:                                # timeout
                ss, cwnd = cwnd / 2, 1.0
            else:
                cwnd = min(cwnd * 2, ss) if cwnd < ss else cwnd + 1
        return out

    reno, tahoe = trace(False), trace(True)
    x = np.arange(len(reno))
    fig, ax = plt.subplots(figsize=(6.6, 5.2))
    ax.axvspan(0, 5, color="#dbeafe", alpha=0.6, lw=0)
    ax.axvspan(5, 17, color="#f1f5f9", alpha=0.9, lw=0)
    ax.axvspan(35, 40, color="#dbeafe", alpha=0.6, lw=0)
    ax.plot(x[16:36], tahoe[16:36], color=MUTED, lw=1.8, ls="--", label="Tahoe (1988)")
    ax.plot(x, reno, color=Reno.color, lw=2.6, marker="o", ms=3.5, label="Reno (1990)")
    ax.step([0, 17, 18, 34, 35, 45], [32, 32, 21, 21, 14, 14], where="post",
            color=RED, lw=1.2, ls=":", label="ssthresh")
    ax.text(2.5, 45, "Slow\nstart", ha="center", fontsize=11, color=Reno.color, fontweight="bold")
    ax.text(11, 45, "Congestion\navoidance", ha="center", fontsize=11, color=INK, fontweight="bold")
    ax.annotate("3 dupACK\ncwnd ÷ 2", xy=(18, 21), xytext=(21.5, 34), fontsize=11,
                arrowprops=dict(arrowstyle="->", color=INK))
    ax.annotate("Timeout\ncwnd = 1", xy=(35.2, 1), xytext=(39.5, 3), fontsize=11,
                arrowprops=dict(arrowstyle="->", color=INK))
    ax.set_xlabel("Thời gian (số RTT)")
    ax.set_ylabel("cwnd (MSS)")
    ax.set_ylim(0, 52)
    ax.set_xlim(0, 45)
    ax.legend(loc="lower left", bbox_to_anchor=(0.12, 0.02))
    save(fig, "phases.png")


def cubic_func():
    C, beta, wmax = 0.4, 0.7, 100
    K = (wmax * (1 - beta) / C) ** (1 / 3)
    t = np.linspace(0, 7.2, 400)
    w = C * (t - K) ** 3 + wmax
    fig, ax = plt.subplots(figsize=(6.6, 5.2))
    ax.axvspan(0, K, color="#ffedd5", lw=0, alpha=0.7)
    ax.axvspan(K, 7.2, color="#fff7ed", lw=0)
    ax.axhline(wmax, color=MUTED, ls="--", lw=1.2)
    ax.plot(t, w, color=Cubic.color, lw=3, label="CUBIC  W(t) = C(t − K)³ + Wmax")
    ax.plot(t, np.minimum(50 + t / 0.1, 150), color=Reno.color, lw=1.8, ls="--",
            label="Reno (RTT = 100 ms)")
    ax.plot([0], [beta * wmax], "o", color=Cubic.color, ms=8)
    ax.plot([K], [wmax], "o", color=INK, ms=7)
    ax.text(0.15, 64, "β·Wmax", color=Cubic.color, fontsize=11)
    ax.text(0.1, wmax + 2, "Wmax (cwnd lúc mất gói)", color=MUTED, fontsize=11)
    ax.annotate(f"K = {K:.1f} s", xy=(K, wmax), xytext=(K + 0.1, 78), fontsize=11,
                arrowprops=dict(arrowstyle="->", color=INK))
    ax.text(K / 2, 132, "Vùng LÕM\ntăng nhanh rồi\nchậm dần gần Wmax", ha="center", fontsize=11)
    ax.text((K + 7.2) / 2, 132, "Vùng LỒI\nthăm dò\nbăng thông mới", ha="center", fontsize=11)
    ax.set_xlabel("Thời gian kể từ lần mất gói gần nhất (s)")
    ax.set_ylabel("cwnd (gói)")
    ax.set_ylim(40, 155)
    ax.set_xlim(0, 7.2)
    ax.legend(loc="lower right")
    save(fig, "cubic_func.png")


def bbr_model():
    bdp, buf, rtprop, btlbw = 100, 100, 60, 100
    x = np.linspace(0, 230, 500)
    rtt = np.where(x < bdp, rtprop, rtprop * x / bdp)
    rate = np.where(x < bdp, btlbw * x / bdp, btlbw)
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(6.6, 6.0), sharex=True)
    for ax in (a1, a2):
        ax.axvspan(0, bdp, color="#f0fdf4", lw=0)
        ax.axvspan(bdp, bdp + buf, color="#fefce8", lw=0)
        ax.axvspan(bdp + buf, 230, color="#fef2f2", lw=0)
        ax.axvline(bdp, color=BBR.color, lw=2)
        ax.axvline(bdp + buf, color=RED, lw=2, ls="--")
    x_ok, x_full = x <= bdp + buf, x >= bdp + buf
    a1.plot(x[x_ok], rtt[x_ok], color=INK, lw=2.6)
    a1.plot(x[x_full], rtt[x_full], color=INK, lw=2.6, ls=":")
    a1.set_ylabel("RTT")
    a1.set_yticks([rtprop], ["RTprop"])
    a1.text(bdp / 2, 150, "app-limited", ha="center", color=MUTED, fontsize=11)
    a1.text(bdp + buf / 2, 150, "bandwidth-\nlimited", ha="center", color=MUTED, fontsize=11)
    a1.text(bdp + buf + 15, 150, "buffer-\nlimited", ha="center", color=MUTED, fontsize=11)
    a1.text(bdp + buf / 2, 100, "hàng đợi\ntăng dần", ha="center", fontsize=11, rotation=0)
    a1.set_ylim(0, 175)
    a2.plot(x, rate, color=INK, lw=2.6)
    a2.set_ylabel("Delivery rate")
    a2.set_yticks([btlbw], ["BtlBw"])
    a2.set_ylim(0, 140)
    a2.set_xticks([bdp, bdp + buf], ["BDP", "BDP + buffer"])
    a2.set_xlabel("Lượng dữ liệu đang bay (inflight)")
    a2.annotate("BBR vận hành ở đây\n(tối ưu Kleinrock)", xy=(bdp, 100), xytext=(4, 108),
                color=BBR.color, fontsize=11, fontweight="bold",
                arrowprops=dict(arrowstyle="->", color=BBR.color))
    a2.annotate("Reno/CUBIC\nmất gói ở đây", xy=(bdp + buf, 100), xytext=(124, 40),
                color=RED, fontsize=11, fontweight="bold",
                arrowprops=dict(arrowstyle="->", color=RED))
    fig.tight_layout()
    save(fig, "bbr_model.png")


# ----------------------------------------------------------- đồ thị từ engine
def engine_fig(cls, name, seconds=40, compare=None, notes=(), inset=False, legend="upper right"):
    env = Env()
    r = run(cls, env, seconds=seconds)
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(6.6, 6.6), sharex=True,
                                 gridspec_kw={"height_ratios": [3, 1.3]})
    thr = env.bdp + env.buffer_pkts
    a1.axhline(env.bdp, color=MUTED, ls="--", lw=1.2)
    a1.axhline(thr, color=RED, ls=":", lw=1.4)
    lab = dict(ha="left", va="center", fontsize=10, zorder=1.5, bbox=dict(fc="white", ec="none", pad=1))
    a1.text(1.5, env.bdp, "BDP", color=MUTED, **lab)
    a1.text(1.5, thr, "BDP + buffer", color=RED, **lab)
    if compare:
        rc = run(compare, env, seconds=seconds)
        a1.plot(rc["t"], rc["inflight"], color="#94a3b8", lw=1.2, label=f"{compare.name} (tham chiếu)")
    if cls is BBR:
        a1.plot(r["t"], r["cwnd"], color=cls.color, lw=1.2, ls="--", alpha=0.7, label="cwnd")
    a1.plot(r["t"], r["inflight"], color=cls.color, lw=2.2, label="Dữ liệu đang bay")
    lt = [t for t, _ in r["loss"]]
    ly = [y for _, y in r["loss"]]
    a1.plot(lt, ly, "x", color=RED, ms=7, mew=2, label="Phát hiện mất gói")
    for text, xy, xytext in notes:
        a1.annotate(text, xy=xy, xytext=xytext, fontsize=11,
                    arrowprops=dict(arrowstyle="->", color=INK))
    a1.set_ylabel("Gói (MSS)")
    a1.set_ylim(0, max(thr * 1.35, min(max(r["inflight"]), 420) * 1.05))
    a1.legend(loc=legend, fontsize=10)
    a2.plot(r["t"], r["rtt"], color=cls.color, lw=1.8)
    a2.axhline(env.rtt_ms, color=MUTED, ls="--", lw=1)
    a2.set_ylim(0, (env.bdp + env.buffer_pkts) / env.cap * 1000 * 1.15)
    a2.set_ylabel("RTT (ms)")
    a2.set_xlabel("Thời gian (s)")
    a2.set_xlim(0, seconds)
    fig.suptitle(f"{cls.name} — 20 Mbps, RTT 60 ms, buffer 100 gói", fontsize=12, color=MUTED)
    if inset:
        ax = a1.inset_axes([0.5, 0.6, 0.47, 0.32])
        n = 150
        ax.plot(r["t"][:n], r["inflight"][:n], color=cls.color, lw=1.8)
        ax.axhline(env.bdp, color=MUTED, ls="--", lw=1)
        ax.set_title("1,5 s đầu: STARTUP → DRAIN", fontsize=9, fontweight="normal")
        ax.tick_params(labelsize=8)
        ax.grid(False)
    fig.tight_layout()
    save(fig, name)
    return r


def compare():
    scen = [("Mặc định", Env()), ("Mất gói\nngẫu nhiên 1%", Env(loss_pct=1)),
            ("RTT 200 ms", Env(rtt_ms=200)), ("Buffer sâu\n400 gói", Env(buffer_pkts=400))]
    algos = (Reno, Cubic, BBR)
    res = {(a, i): run(a, e, seconds=60) for a in algos for i, (_, e) in enumerate(scen)}
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(12.5, 4.3))
    x = np.arange(len(scen))
    for j, a in enumerate(algos):
        tp = [res[a, i]["tput_mbps"] for i in range(len(scen))]
        rt = [res[a, i]["avg_rtt_ms"] for i in range(len(scen))]
        b1 = a1.bar(x + (j - 1) * 0.26, tp, 0.25, color=a.color, label=a.name)
        b2 = a2.bar(x + (j - 1) * 0.26, rt, 0.25, color=a.color, label=a.name)
        a1.bar_label(b1, fmt="%.0f", fontsize=9, padding=2)
        a2.bar_label(b2, fmt="%.0f", fontsize=9, padding=2)
    for ax, title in ((a1, "Throughput trung bình (Mbps) — link 20 Mbps"),
                      (a2, "RTT trung bình (ms) — thấp hơn là tốt hơn")):
        ax.set_xticks(x, [s for s, _ in scen])
        ax.set_title(title, fontsize=12, loc="left")
        ax.grid(axis="x", visible=False)
    a1.set_ylim(0, 24)
    fig.tight_layout(rect=(0, 0.08, 1, 1))
    fig.legend(*a1.get_legend_handles_labels(), loc="lower center", ncol=3, fontsize=11)
    save(fig, "compare.png")


def cover():
    env = Env()
    fig, axes = plt.subplots(3, 1, figsize=(6, 7.5), sharex=True)
    for ax, cls in zip(axes, (Reno, Cubic, BBR)):
        r = run(cls, env, seconds=30)
        t, y = np.array(r["t"]), np.array(r["inflight"])
        t, y = t[t >= 1.5], y[t >= 1.5]                  # bỏ pha khởi động cho gọn
        ax.fill_between(t, y, color=cls.color, alpha=0.12, lw=0)
        ax.plot(t, y, color=cls.color, lw=2.6)
        ax.text(2, 255, cls.name.replace(" (v1)", ""), fontsize=15, fontweight="bold", color=cls.color)
        ax.set_ylim(0, 290)
        ax.set_axis_off()
    fig.subplots_adjust(hspace=0.05)
    save(fig, "cover.png")


if __name__ == "__main__":
    sliding_window()
    phases()
    cubic_func()
    bbr_model()
    engine_fig(Reno, "reno.png", notes=[
        ("Slow start\nvượt ngưỡng", (0.5, 330), (3, 360)),
        ("+1 MSS / RTT", (8, 152), (9.5, 245)),
        ("3 dupACK → ÷2", (22.2, 98), (25, 40)),
    ])
    engine_fig(Cubic, "cubic.png", compare=Reno, notes=[
        ("bám sát Wmax", (5.5, 172), (3.2, 245)),
        ("lồi: thăm dò", (10.2, 192), (12, 262)),
    ])
    engine_fig(BBR, "bbr.png", inset=True, legend="lower right", notes=[
        ("PROBE_RTT (cwnd = 4)\nđo lại RTprop", (18.4, 5), (4, 40)),
        ("PROBE_BW: gain\n1.25 → 0.75 → 1 ×6", (9.1, 124), (4, 160)),
    ])
    compare()
    cover()
