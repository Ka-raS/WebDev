"""Mô phỏng fluid một luồng TCP đi qua một nút cổ chai drop-tail.

    sender --(cwnd, pacing)--> [hàng đợi drop-tail: `buffer` gói] --(băng thông C)--> receiver
                   ^------------------------ ACK sau RTT cơ sở ------------------------'

- Bước thời gian rời rạc `dt` (mặc định 1 ms), lượng dữ liệu tính bằng gói (MSS = 1500 B).
- RTT mẫu = RTT cơ sở + độ trễ hàng đợi; mất gói được phát hiện sau ~1 RTT (3 dupACK).
- Mỗi thuật toán chạy trên một đường truyền riêng với cùng tham số môi trường,
  nên các đồ thị có thể so sánh trực tiếp với nhau.
"""

import math
import random
from collections import deque

MSS_BITS = 1500 * 8


class Env:
    """Tham số môi trường, có thể thay đổi trong lúc mô phỏng đang chạy."""

    def __init__(self, bw_mbps=20.0, rtt_ms=60.0, buffer_pkts=100.0, loss_pct=0.0):
        self.bw_mbps = bw_mbps
        self.rtt_ms = rtt_ms
        self.buffer_pkts = buffer_pkts
        self.loss_pct = loss_pct

    @property
    def cap(self):
        """Băng thông nút cổ chai (gói/giây)."""
        return self.bw_mbps * 1e6 / MSS_BITS

    @property
    def base_rtt(self):
        return self.rtt_ms / 1000.0

    @property
    def bdp(self):
        """Bandwidth-delay product (gói)."""
        return self.cap * self.base_rtt


# --------------------------------------------------------------------------- Reno
class Reno:
    name = "TCP Reno"
    color = "#2563eb"

    def __init__(self):
        self.cwnd = 10.0
        self.ssthresh = math.inf
        self.recover_point = 0.0
        self.in_recovery = False

    def pacing_rate(self, flow):
        return None

    def on_ack(self, acked, rtt, now, flow):
        self.in_recovery = flow.resolved < self.recover_point
        if self.cwnd < self.ssthresh:
            self.cwnd += acked  # slow start: +1 MSS mỗi ACK
        else:
            self.cwnd += acked / self.cwnd  # congestion avoidance: +1 MSS mỗi RTT

    def on_loss(self, now, flow, seq):
        if seq <= self.recover_point:  # gói gửi trước lần giảm trước → bỏ qua (NewReno)
            return
        self.ssthresh = max(self.cwnd / 2, 2.0)
        self.cwnd = self.ssthresh  # fast recovery: cwnd = cwnd / 2
        self.recover_point = flow.sent
        self.in_recovery = True

    def on_rto(self, now, flow):
        self.ssthresh = max(self.cwnd / 2, 2.0)
        self.cwnd = 1.0
        self.recover_point = flow.sent

    @property
    def state(self):
        if self.cwnd < self.ssthresh:
            return "Slow start"
        if self.in_recovery:
            return "Fast recovery"
        return "Congestion avoidance"

    def info(self):
        ss = "∞" if math.isinf(self.ssthresh) else f"{self.ssthresh:.0f}"
        return {
            "Trạng thái": self.state,
            "cwnd": f"{self.cwnd:.0f} gói",
            "ssthresh": ss,
        }


# -------------------------------------------------------------------------- CUBIC
class Cubic:
    name = "TCP CUBIC"
    color = "#ea580c"
    C = 0.4
    BETA = 0.7

    def __init__(self):
        self.cwnd = 10.0
        self.ssthresh = math.inf
        self.w_max = 0.0
        self.k = 0.0
        self.w_est = 0.0
        self.cwnd_prior = 0.0  # cwnd ngay trước lần giảm gần nhất
        self.epoch = None  # thời điểm bắt đầu epoch hiện tại
        self.recover_point = 0.0
        self.state = "Slow start"
        self.now = 0.0

    def pacing_rate(self, flow):
        return None

    def w_cubic(self, t):
        return self.C * (t - self.k) ** 3 + self.w_max

    def on_ack(self, acked, rtt, now, flow):
        self.now = now
        if self.cwnd < self.ssthresh:
            self.cwnd += acked
            self.state = "Slow start"
            return
        if self.epoch is None:
            self.epoch = now
            if self.cwnd < self.w_max:
                self.k = ((self.w_max - self.cwnd) / self.C) ** (1 / 3)
            else:
                self.k, self.w_max = 0.0, self.cwnd
            self.w_est = self.cwnd
        t = now - self.epoch
        # Ước lượng cửa sổ của Reno với cùng thời gian (vùng Reno-friendly, RFC 9438)
        alpha = (
            3 * (1 - self.BETA) / (1 + self.BETA)
            if self.w_est < self.cwnd_prior
            else 1.0
        )
        self.w_est += alpha * acked / self.cwnd
        if self.w_cubic(t) < self.w_est:
            self.cwnd = self.w_est
            self.state = "Reno-friendly"
        else:
            target = min(max(self.w_cubic(t + flow.rtt), self.cwnd), 1.5 * self.cwnd)
            self.cwnd += (target - self.cwnd) / self.cwnd * acked
            self.state = "Lõm (concave)" if t < self.k else "Lồi (convex)"

    def on_loss(self, now, flow, seq):
        if seq <= self.recover_point:
            return
        self.epoch = None
        self.cwnd_prior = self.cwnd
        # fast convergence: nhường băng thông khi Wmax giảm dần
        self.w_max = (
            self.cwnd * (1 + self.BETA) / 2 if self.cwnd < self.w_max else self.cwnd
        )
        self.ssthresh = max(self.cwnd * self.BETA, 2.0)
        self.cwnd = self.ssthresh
        self.recover_point = flow.sent

    def on_rto(self, now, flow):
        self.epoch = None
        self.w_max = self.cwnd_prior = self.cwnd
        self.ssthresh = max(self.cwnd * self.BETA, 2.0)
        self.cwnd = 1.0
        self.recover_point = flow.sent

    def info(self):
        t = "—" if self.epoch is None else f"{self.now - self.epoch:.1f} s"
        return {
            "Vùng": self.state,
            "cwnd": f"{self.cwnd:.0f} gói",
            "Wmax": f"{self.w_max:.0f} gói",
            "K": f"{self.k:.2f} s",
            "t (từ lần mất)": t,
        }


# ---------------------------------------------------------------------------- BBR
class BBR:
    name = "TCP BBR (v1)"
    color = "#16a34a"
    HIGH_GAIN = 2 / math.log(2)  # ≈ 2.885
    CYCLE = (1.25, 0.75, 1, 1, 1, 1, 1, 1)
    RTPROP_WIN = 10.0  # s
    PROBE_RTT_TIME = 0.2  # s

    def __init__(self):
        self.cwnd = 10.0
        self.state = "STARTUP"
        self.pacing_gain = self.cwnd_gain = self.HIGH_GAIN
        self.btlbw = 0.0  # gói/s
        self.rtprop = math.inf  # s
        self.filled_pipe = False
        self._bw_rounds = deque(maxlen=10)  # max-filter trên 10 round
        self._round_max = 0.0
        self._round_start = 0.0
        self._rtprop_stamp = 0.0
        self._full_bw = 0.0
        self._full_bw_cnt = 0
        self._cycle_idx = 0
        self._cycle_stamp = 0.0
        self._loss_in_cycle = False
        self._probe_rtt_done = None
        self._prior_cwnd = 0.0
        self._restore_at = None

    def bdp(self):
        return self.btlbw * self.rtprop if self.btlbw > 0 else 0.0

    def pacing_rate(self, flow):
        bw = self.btlbw if self.btlbw > 0 else self.cwnd / flow.rtt
        return self.pacing_gain * bw

    def _set(self, state, pacing_gain, cwnd_gain):
        self.state, self.pacing_gain, self.cwnd_gain = state, pacing_gain, cwnd_gain

    def _enter_probe_bw(self, now, flow):
        self._set("PROBE_BW", 1.0, 2.0)
        self._cycle_idx = flow.rng.choice((0, 2, 3, 4, 5, 6, 7))
        self.pacing_gain = self.CYCLE[self._cycle_idx]
        self._cycle_stamp = now
        self._loss_in_cycle = False

    def on_ack(self, acked, rtt, now, flow):
        # 1. Cập nhật mô hình mạng: RTprop = min RTT (10 s), BtlBw = max delivery rate (10 round)
        expired = now > self._rtprop_stamp + self.RTPROP_WIN
        if rtt <= self.rtprop or expired:
            self.rtprop, self._rtprop_stamp = rtt, now
        self._round_max = max(self._round_max, flow.rate)
        round_end = now - self._round_start >= flow.rtt
        if round_end:
            self._bw_rounds.append(self._round_max)
            self._round_max = 0.0
            self._round_start = now
        self.btlbw = max(max(self._bw_rounds, default=0.0), self._round_max)
        bdp = self.bdp()

        # 2. Máy trạng thái
        if round_end and not self.filled_pipe:
            if self.btlbw >= self._full_bw * 1.25:
                self._full_bw, self._full_bw_cnt = self.btlbw, 0
            else:
                self._full_bw_cnt += 1
                self.filled_pipe = self._full_bw_cnt >= 3
        if self.state == "STARTUP" and self.filled_pipe:
            self._set("DRAIN", 1 / self.HIGH_GAIN, self.HIGH_GAIN)
        if self.state == "DRAIN" and flow.inflight <= bdp:
            self._enter_probe_bw(now, flow)
        if self.state == "PROBE_BW":
            g = self.pacing_gain
            elapsed = now - self._cycle_stamp > self.rtprop
            if g > 1:
                advance = elapsed and (self._loss_in_cycle or flow.inflight >= g * bdp)
            elif g < 1:
                advance = elapsed or flow.inflight <= bdp
            else:
                advance = elapsed
            if advance:
                self._cycle_idx = (self._cycle_idx + 1) % len(self.CYCLE)
                self.pacing_gain = self.CYCLE[self._cycle_idx]
                self._cycle_stamp = now
                self._loss_in_cycle = False
        if expired and self.state != "PROBE_RTT":
            self._prior_cwnd = max(self._prior_cwnd, self.cwnd)
            self._set("PROBE_RTT", 1.0, 1.0)
            self._probe_rtt_done = None
        if self.state == "PROBE_RTT":
            if self._probe_rtt_done is None:
                if flow.inflight <= 4:
                    self._probe_rtt_done = now + max(self.PROBE_RTT_TIME, self.rtprop)
            elif now >= self._probe_rtt_done:
                self._rtprop_stamp = now
                self.cwnd = max(self.cwnd, self._prior_cwnd)
                self._prior_cwnd = 0.0
                if self.filled_pipe:
                    self._enter_probe_bw(now, flow)
                else:
                    self._set("STARTUP", self.HIGH_GAIN, self.HIGH_GAIN)
        if self.state == "PROBE_RTT":
            self.cwnd = 4.0
            return

        # 3. cwnd = cwnd_gain × BDP
        if self._restore_at is not None and now >= self._restore_at:
            self.cwnd = max(self.cwnd, self._prior_cwnd)
            self._prior_cwnd, self._restore_at = 0.0, None
        target = max(self.cwnd_gain * bdp, 4.0)
        if self.filled_pipe:
            self.cwnd = min(self.cwnd + acked, target)
        elif self.cwnd < target or flow.delivered < 10:
            self.cwnd += acked
        self.cwnd = max(self.cwnd, 4.0)

    def on_loss(self, now, flow, seq):
        self._loss_in_cycle = True  # BBRv1 không giảm cwnd khi mất gói

    def on_rto(self, now, flow):
        self._prior_cwnd = self.cwnd
        self.cwnd = 1.0
        self._restore_at = now + flow.rtt

    def info(self):
        rtprop = "—" if math.isinf(self.rtprop) else f"{self.rtprop * 1000:.0f} ms"
        return {
            "Trạng thái": self.state,
            "pacing_gain": f"{self.pacing_gain:.2f}",
            "BtlBw": f"{self.btlbw * MSS_BITS / 1e6:.1f} Mbps",
            "RTprop": rtprop,
            "BDP ước lượng": f"{self.bdp():.0f} gói",
        }


# --------------------------------------------------------------------------- Flow
class Flow:
    """Một luồng TCP + đường truyền riêng của nó."""

    def __init__(self, cc, env, seed=1):
        self.cc = cc
        self.env = env
        self.rng = random.Random(seed)
        self.now = 0.0
        self._ticks = 0
        self.q = 0.0  # gói trong hàng đợi nút cổ chai
        self.inflight = 0.0  # gói đã gửi, chưa ACK / chưa phát hiện mất
        self.sent = 0.0  # tích lũy
        self.delivered = 0.0  # tích lũy
        self.lost = 0.0  # tích lũy (đã phát hiện)
        self.rtt = env.base_rtt  # RTT mẫu gần nhất (gồm trễ hàng đợi)
        self.rate = 0.0  # delivery rate (gói/s) đo trên ~1 RTT
        self.acks = deque()  # [t_đến, số gói, rtt]
        self.losses = deque()  # [t_phát_hiện, số gói, seq lúc gửi]
        self.loss_marks = deque()  # (t, inflight) để vẽ
        self.loss_events = 0
        self._last_mark = -math.inf
        self._rate_hist = deque([(0.0, 0.0)])
        self._tput_hist = deque([(0.0, 0.0)])
        self._stall_until = 0.0
        self._rto_pending = False

    def _schedule_loss(self, n):
        self.losses.append([self.now + self.rtt, n, self.sent])

    def step(self, dt):
        env, cc = self.env, self.cc
        cap = env.cap
        self._ticks += 1
        now = self.now = self._ticks * dt
        due = now + 1e-9  # tránh lệch do sai số dấu phẩy động

        # 1. Gửi: giới hạn bởi cwnd và (nếu có) pacing rate
        if self._rto_pending and now >= self._stall_until:
            self._rto_pending = False
            cc.on_rto(now, self)
        if now >= self._stall_until:
            send = max(0.0, cc.cwnd - self.inflight)
            pace = cc.pacing_rate(self)
            if pace is not None:
                send = min(send, pace * dt)
            if send > 0:
                self.inflight += send
                self.sent += send
                p = env.loss_pct / 100
                if p > 0 and self.rng.random() < 1 - (1 - p) ** send:
                    lost = min(send, 1.0)  # mất gói ngẫu nhiên (nhiễu đường truyền)
                    send -= lost
                    self._schedule_loss(lost)
                self.q += send
                if self.q > env.buffer_pkts:  # tràn buffer → drop-tail
                    self._schedule_loss(self.q - env.buffer_pkts)
                    self.q = env.buffer_pkts

        # 2. Nút cổ chai phục vụ với tốc độ C
        out = min(self.q, cap * dt)
        if out > 0:
            self.q -= out
            self.acks.append([now + env.base_rtt, out, env.base_rtt + self.q / cap])

        # 3. Nhận ACK
        acked, rtt = 0.0, None
        acks = self.acks
        while acks and acks[0][0] <= due:
            _, n, rtt = acks.popleft()
            acked += n
        if acked > 0:
            self.inflight -= acked
            self.delivered += acked
            self.rtt = rtt
            h = self._rate_hist
            h.append((now, self.delivered))
            while len(h) > 2 and h[1][0] <= due - self.rtt:
                h.popleft()
            t0, d0 = h[0]
            self.rate = (self.delivered - d0) / (now - t0)
            cc.on_ack(acked, rtt, now, self)

        # 4. Phát hiện mất gói (3 dupACK)
        while self.losses and self.losses[0][0] <= due:
            _, n, seq = self.losses.popleft()
            if now - self._last_mark > self.rtt:
                self._last_mark = now
                self.loss_events += 1
                self.loss_marks.append((now, self.inflight))
            self.inflight -= n
            self.lost += n
            cc.on_loss(now, self, seq)
        if self.inflight < 0:
            self.inflight = 0.0

    # ---- sự kiện do người dùng kích hoạt
    def inject_loss(self, n=1.0):
        """Làm rơi n gói đang bay; sender phát hiện qua 3 dupACK sau ~1 RTT."""
        take = min(n, self.q)
        self.q -= take
        rest = n - take
        for a in reversed(self.acks):
            if rest <= 0:
                break
            d = min(rest, a[1])
            a[1] -= d
            rest -= d
        if n - rest > 0:
            self._last_mark = -math.inf  # luôn đánh dấu sự kiện người dùng tạo ra
            self._schedule_loss(n - rest)

    def inject_rto(self):
        """Mất toàn bộ gói đang bay (vd. đứt link tạm thời) → sender chờ hết RTO."""
        self.q = 0.0
        self.acks.clear()
        self.losses.clear()
        self.loss_marks.append((self.now, self.inflight))
        self.loss_events += 1
        self.lost += self.inflight
        self.inflight = 0.0
        self._stall_until = self.now + max(0.2, 2 * self.rtt)
        self._rto_pending = True

    @property
    def resolved(self):
        """Số gói đã có kết quả (được ACK hoặc phát hiện mất)."""
        return self.delivered + self.lost

    # ---- thống kê
    def throughput_mbps(self, window=1.0):
        h = self._tput_hist
        h.append((self.now, self.delivered))
        while len(h) > 2 and h[1][0] <= self.now - window:
            h.popleft()
        t0, d0 = h[0]
        return (
            0.0
            if self.now <= t0
            else (self.delivered - d0) / (self.now - t0) * MSS_BITS / 1e6
        )


def run(cc_cls, env=None, seconds=40.0, dt=0.001, every=0.01, seed=1, events=()):
    """Chạy không giao diện, trả về chuỗi thời gian để vẽ đồ thị.

    events: danh sách (thời điểm, "loss" | "rto").
    """
    env = env or Env()
    f = Flow(cc_cls(), env, seed)
    events = sorted(events)
    rec = {k: [] for k in ("t", "inflight", "cwnd", "rtt", "state", "queue")}
    n_every = max(1, round(every / dt))
    for i in range(1, int(round(seconds / dt)) + 1):
        while events and events[0][0] <= f.now:
            _, kind = events.pop(0)
            f.inject_loss(3) if kind == "loss" else f.inject_rto()
        f.step(dt)
        if i % n_every == 0:
            rec["t"].append(f.now)
            rec["inflight"].append(f.inflight)
            rec["cwnd"].append(f.cc.cwnd)
            rec["rtt"].append(f.rtt * 1000)
            rec["state"].append(f.cc.state)
            rec["queue"].append(f.q)
    rec["loss"] = list(f.loss_marks)
    rec["tput_mbps"] = f.delivered * MSS_BITS / 1e6 / seconds
    rec["avg_rtt_ms"] = sum(rec["rtt"]) / len(rec["rtt"])
    return rec
