# Kiến thức nền cho bài thuyết trình

Mình giảng theo đúng thứ tự trên slide. Mọi ví dụ dùng cùng một đường truyền như trong demo: **20 Mbps, RTT 60 ms, buffer 100 gói, mỗi gói 1500 byte**.

---

## Phần 1 — Window Management

### Vấn đề: bên gửi không nhìn thấy mạng
Hình dung bạn bơm nước vào một đường ống dài mà không nhìn thấy đầu bên kia. Bơm chậm thì phí công suất ống. Bơm quá mạnh thì nước tràn ở chỗ ống hẹp nhất (router), tức là mất gói.

Năm 1986, các máy gửi cứ bơm hết sức. Gói bị mất thì chúng gửi lại, mạng càng nghẽn, rồi lại mất thêm. Kết quả là tốc độ tụt khoảng 1000 lần. Đó là **congestion collapse**.

### cwnd: "được phép có bao nhiêu gói đang bay"
- **cwnd (congestion window)** là số gói tối đa bên gửi được phép gửi đi mà chưa nhận ACK.
- Cứ sau mỗi RTT (thời gian gói đi và ACK quay về), bên gửi gửi được khoảng cwnd gói.

  **Throughput ≈ cwnd / RTT**

  Ví dụ: cwnd = 100 gói, RTT = 60 ms → 100 × 1500 byte / 0,06 s = 2,5 MB/s = **20 Mbps**.
- **rwnd** là giới hạn do bên nhận đặt ra, để bên nhận không bị tràn bộ nhớ. Bên gửi dùng **min(cwnd, rwnd)**. Bài thuyết trình tập trung vào cwnd.

### BDP: dung tích của "đường ống"
**BDP = băng thông × RTT tối thiểu**

Ví dụ: 20 Mbps = 1667 gói/s. Nhân với 0,06 s được **BDP = 100 gói**. Nghĩa là cần đúng 100 gói đang bay thì đường truyền mới được dùng hết.

Ba trường hợp, với buffer router là 100 gói:

| Số gói đang bay | Chuyện gì xảy ra |
|---|---|
| < 100 (BDP) | Đường truyền còn trống, **lãng phí** |
| 100 → 200 | Đường truyền đã đầy. Phần dư xếp hàng trong buffer, **RTT tăng** (60 → 120 ms) |
| > 200 (BDP + buffer) | Buffer tràn, **mất gói** |

→ Điểm lý tưởng là **đúng bằng BDP**: tốc độ tối đa và chưa phải xếp hàng. Cả ba thuật toán đều đang đi tìm con số này, mỗi cái một cách.

### Các pha của cwnd
- **Slow start:** mỗi ACK cộng thêm 1 gói, nên cwnd gấp đôi sau mỗi RTT: 1 → 2 → 4 → 8 → 16…
  Tên "slow" gây hiểu nhầm, thật ra pha này tăng rất nhanh. Nó chỉ "chậm" so với cách cũ là gửi hết một lúc.
- **Congestion avoidance:** khi cwnd chạm ngưỡng `ssthresh` thì chuyển sang tăng **+1 gói mỗi RTT**, rất thận trọng.
- **Tín hiệu tắc nghẽn:**
  - **3 duplicate ACK:** bên nhận cứ báo "tôi vẫn đang chờ gói số 5". Như vậy gói 6, 7, 8 vẫn tới nơi, chỉ riêng gói 5 bị mất → mạng **nghẽn nhẹ**.
  - **Timeout:** không nhận được ACK nào cả → mạng **nghẽn nặng** hoặc đứt.
- **AIMD** (tăng cộng, giảm nhân): tăng từ từ, gặp nghẽn thì giảm mạnh. Ví dụ hai luồng đang chia 150/50. Cả hai cùng +1 mỗi RTT thì khoảng cách không đổi. Nhưng khi cùng chia đôi thì khoảng cách cũng bị chia đôi (75/25). Lặp lại nhiều lần, hai luồng dần tiến về chia đều. Đây là lý do AIMD **công bằng**.

---

## Phần 2 — TCP Reno (1990)

### Ý tưởng
"Cứ tăng dần cho đến khi mất gói, rồi lùi một nửa." Giống lái xe tăng ga từ từ, thấy kẹt thì phanh gấp.

### Ví dụ chạy tay (khớp với đồ thị trong demo)
1. cwnd tăng lên **200** (= BDP + buffer), buffer tràn, mất gói.
2. Nhận 3 dupACK → `cwnd = 200 / 2 = 100`.
3. Tăng lại +1 gói mỗi RTT: 100 → 101 → … → 200. Việc này mất 100 RTT. Vì buffer đầy dần, RTT trung bình khoảng 90 ms, nên mất khoảng **9 giây**.
4. Lại mất gói, lặp lại. Kết quả là **đồ thị răng cưa** với chu kỳ khoảng 9 giây.

Điểm mới so với Tahoe (1988): Tahoe **mọi** lần mất gói đều đưa cwnd về 1 và slow start lại từ đầu. Reno phân biệt được nghẽn nhẹ (3 dupACK) nên chỉ chia đôi.

### Công thức Mathis: vì sao Reno "sợ" mất gói
**Throughput ≈ (MSS / RTT) × 1,22 / √p**

Ví dụ với Wi‑Fi nhiễu, mất 1% gói (p = 0,01):
1,22 / √0,01 = 12,2 gói mỗi RTT → 12,2 × 1500 × 8 / 0,06 ≈ **2,4 Mbps**.
Đường truyền 20 Mbps mà Reno chỉ dùng được khoảng 2,4 Mbps, **dù mạng hoàn toàn không nghẽn**. Demo cho ra khoảng 2,6 Mbps, khớp với công thức.

### Các nhược điểm, kèm ví dụ
- **Mạng nhanh thì quá chậm:** với 10 Gbps và RTT 100 ms, cwnd cần khoảng 83.333 gói. Sau một lần mất gói, cwnd còn 41.667 và phải tăng +1 mỗi RTT, tức 41.667 × 0,1 s ≈ **70 phút** mới lấy lại được tốc độ.
- **Bất công theo RTT:** luồng A có RTT 20 ms tăng +1 mỗi 20 ms, luồng B có RTT 200 ms tăng +1 mỗi 200 ms. A tăng nhanh gấp 10 lần và chiếm phần lớn băng thông.
- **Bufferbloat:** Reno luôn đẩy dữ liệu cho tới khi buffer tràn, nên buffer gần như lúc nào cũng đầy. RTT bị đẩy từ 60 lên tới 120 ms.

---

## Phần 3 — TCP CUBIC (2005)

### Ý tưởng
CUBIC có hai điểm khác Reno:
1. **cwnd phụ thuộc thời gian thực** kể từ lần mất gói cuối, không phụ thuộc số ACK. Nhờ vậy luồng có RTT dài không bị thiệt.
2. **Nhớ Wmax**, là cwnd lúc bị mất gói, nghĩa là "mức vừa gây nghẽn lần trước". Hãy hình dung leo lại một ngọn đồi đã từng té:
   - khi còn xa đỉnh cũ thì chạy nhanh;
   - khi gần đỉnh cũ thì đi chậm, dò từng bước (vùng **lõm**);
   - vượt qua đỉnh cũ mà vẫn ổn thì tăng tốc tìm đỉnh mới (vùng **lồi**).

### Công thức và ví dụ số
**W(t) = C·(t − K)³ + Wmax**, với C = 0,4 và β = 0,7.

Giả sử mất gói khi cwnd = **200**:
- cwnd giảm còn 200 × 0,7 = **140**. Reno sẽ xuống 100.
- **K = ∛(Wmax·(1−β)/C) = ∛(200 × 0,3 / 0,4) = ∛150 ≈ 5,3 giây.** Đây là thời gian để quay lại Wmax.

| t (giây) | W(t) | Nhận xét |
|---|---|---|
| 0 | 140 | vừa giảm |
| 1 | ≈ 168 | tăng rất nhanh |
| 3 | ≈ 195 | chậm dần |
| 5,3 | 200 | đi gần như ngang quanh Wmax |
| 7 | ≈ 202 | bắt đầu thăm dò lên |

→ CUBIC ở gần ngưỡng lâu hơn Reno nên dùng đường truyền tốt hơn. Trên mạng lớn, nó hồi phục trong vài giây chứ không mất hàng chục phút.

**Vùng Reno-friendly:** CUBIC luôn tính song song "nếu là Reno thì cwnd bây giờ là bao nhiêu", rồi lấy giá trị lớn hơn. Nhờ vậy trên mạng nhỏ CUBIC không bao giờ kém Reno.

### Nhược điểm
CUBIC **vẫn coi mất gói là tắc nghẽn**. Vì vậy:
- nó vẫn lấp đầy buffer, thậm chí RTT còn cao hơn Reno vì nó bám sát ngưỡng lâu hơn;
- khi mất gói ngẫu nhiên 1%, nó cũng chỉ còn khoảng 3 Mbps như Reno.

---

## Phần 4 — TCP BBR (2016, Google)

### Ý tưởng: đo đường ống thay vì chờ nó tràn
Reno và CUBIC giống người lái xe chỉ biết "đâm vào xe trước rồi mới phanh". BBR giống người lái xe **nhìn đồng hồ**. Nó liên tục đo hai con số:
- **BtlBw:** tốc độ giao hàng lớn nhất đo được trong khoảng 10 RTT gần nhất. Ví dụ đo ra 20 Mbps.
- **RTprop:** RTT nhỏ nhất trong 10 giây gần nhất. Ví dụ 60 ms, đây là RTT khi chưa có hàng đợi.

→ **BDP = 20 Mbps × 60 ms = 100 gói**. BBR giữ khoảng 100 gói đang bay: đúng điểm lý tưởng ở Phần 1, không thừa không thiếu.

Hai cơ chế điều khiển:
- **Pacing:** gói được **giãn đều** với tốc độ BtlBw, khoảng 1667 gói/s, thay vì gửi dồn một cục.
- **cwnd = 2 × BDP = 200:** chỉ là "rào an toàn", không phải cơ chế điều khiển chính.

### Máy trạng thái, kèm ví dụ
1. **STARTUP:** gửi nhanh gấp khoảng 2,89 lần tốc độ ước lượng, nên tốc độ tăng gấp đôi mỗi RTT. Khi 3 vòng liên tiếp đo được tốc độ không tăng thêm 25% thì kết luận "ống đã đầy".
2. **DRAIN:** STARTUP đã lỡ làm đầy buffer, nên BBR gửi chậm lại để xả hàng đợi.
3. **PROBE_BW:** chế độ chạy chính. Chu kỳ 8 nhịp, mỗi nhịp khoảng 1 RTT:
   - Nhịp **×1,25:** gửi nhanh hơn 25%, tức thêm khoảng 25 gói. Nếu tốc độ giao hàng **không tăng**, băng thông vẫn là 20 Mbps, 25 gói đó chỉ nằm chờ trong buffer.
   - Nhịp **×0,75:** gửi chậm hơn 25% để xả đúng 25 gói vừa dư.
   - 6 nhịp **×1:** chạy đều.
   - Nếu mạng vừa được nâng lên 25 Mbps thì ở nhịp ×1,25, tốc độ đo được sẽ tăng lên 25. BBR tự cập nhật BtlBw.
   - Đây là các gai nhỏ đều đặn trên đồ thị BBR.
4. **PROBE_RTT:** cứ khoảng 10 giây, cwnd giảm còn 4 gói trong 200 ms. Lý do: chỉ khi hàng đợi trống mới đo được RTT gốc thật sự. Đây là cái hố sâu trên đồ thị.

### Vì sao BBR không sợ mất gói ngẫu nhiên
Khi mất 1% gói do nhiễu Wi‑Fi, tốc độ giao hàng đo được vẫn khoảng 20 Mbps. Mô hình của BBR không đổi, nên nó **không giảm tốc**. Reno và CUBIC thì chia đôi hoặc giảm 30% mỗi lần mất gói, nên tụt còn khoảng 3 Mbps.

### Nhược điểm (chủ yếu ở BBRv1)
- **Buffer nông**, ví dụ 10 gói: nhịp ×1,25 đẩy dư 25 gói nhưng buffer chỉ chứa 10, nên liên tục mất gói. BBRv1 lại không giảm tốc, dẫn tới **truyền lại rất nhiều**. Chọn preset "Buffer nông" trong demo sẽ thấy dấu × dày đặc.
- **Bất công với CUBIC:** chạy chung một đường, hai bên chia băng thông lệch nhau tuỳ độ sâu của buffer.
- **BBRv2/v3** đã thêm cơ chế phản ứng khi tỉ lệ mất gói vượt khoảng 2%, và hỗ trợ ECN.

---

## Tóm tắt một câu cho mỗi thuật toán
- **Reno:** "Tăng từng bước, gặp nghẽn thì chia đôi." Đơn giản nhưng chậm và nhạy với mất gói.
- **CUBIC:** "Nhớ chỗ từng nghẽn, lao nhanh tới đó rồi dò cẩn thận." Nhanh hơn, nhưng vẫn làm đầy buffer.
- **BBR:** "Đo kích thước đường ống rồi bơm vừa đúng." Độ trễ thấp và chịu được nhiễu, nhưng phức tạp và có vấn đề công bằng.

## Câu hỏi hay gặp khi thuyết trình
- **"Vì sao không dùng BBR cho tất cả?"** → Nó có vấn đề công bằng với CUBIC, dễ gây mất gói ở buffer nông, và vẫn đang được chuẩn hoá.
- **"Slow start sao lại gọi là slow?"** → Nó chậm so với cách gửi cả cửa sổ một lúc thời trước 1988. Về bản chất nó tăng theo hàm mũ.
- **"Mô phỏng có chính xác không?"** → Đây là mô hình đơn giản hoá, mỗi thuật toán chạy trên một đường truyền riêng. Mục đích là thấy đúng **hình dạng hành vi**, không phải đo số liệu thật. Số liệu vẫn khớp công thức Mathis, khoảng 2,4 Mbps ở mức mất gói 1%.
- **"Vì sao CUBIC mặc định trên Linux mà Google lại dùng BBR?"** → CUBIC an toàn và công bằng trên đa số mạng. Google tự kiểm soát máy chủ và phục vụ nhiều người dùng di động, mạng nhiễu, nên họ hưởng lợi nhiều từ BBR.