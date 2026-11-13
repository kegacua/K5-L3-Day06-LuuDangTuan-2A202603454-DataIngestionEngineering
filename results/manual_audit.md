# Bảng nhãn đánh giá thủ công (Manual Audit)

- **Người chấm:** Lưu Đăng Tuấn (`2A202603454`) — tác giả pipeline và benchmark.
- **Tuyên bố thiên lệch (Bias disclosure):** Vì chỉ có một người chấm kiêm tác giả, điểm thủ công có nguy cơ thiên lệch xác nhận về phía giả thuyết ban đầu (`B` tốt hơn `A` về độ mạch lạc, `C` tốt hơn `B` ở các câu cần lọc niên độ/chương). Để giảm thiểu, toàn bộ 10 vị trí coherence (`L01`–`L10`) và 20 câu hỏi (`q01`–`q20`) đã được khóa cố định trong `benchmark/` **trước khi chạy truy xuất**, và bảng dưới đây ghi nguyên văn lỗi biên của cả `B`/`C` (ví dụ `L01`, `L03`, `L08`) chứ không làm đẹp điểm.
- **Nguồn đối chiếu:** [`results/coherence_samples.json`](coherence_samples.json), [`results/test_audit_sheet.json`](test_audit_sheet.json), [`results/traces.json`](traces.json), [`data/manifest.json`](../data/manifest.json).

---

## 1. Chunk Coherence (10 vị trí khóa trước `L01`–`L10`)

Thang điểm (`GUIDE.md`): `0` = bị cắt giữa ý/thiếu chủ thể làm không hiểu hoặc cụt hai đầu; `1` = hiểu một phần, thiếu ngữ cảnh hoặc cụt biên/chen chú thích; `2` = tự hiểu được và giữ trọn ý.

| ID | Nguồn & Trang | Neo văn bản (`anchor_phrase`) | A (0/1/2) | B (0/1/2) | C (0/1/2) | Ghi chú quan sát thực tế từ chunk |
|---|---|---|---:|---:|---:|---|
| L01 | `wb-diemlai-2023-08` p.11 | `của Việt Nam giảm còn 3,7%` | 1 | 1 | 1 | **A** (`p011::c000`, 1400): cắt `...giai đoạn phục` và cắt ngang chú thích 1 `trong Q1-2`. **B/C** (`p011::c000`, 1549): giữ trọn chú thích 1 tới `vào Q2-2023.`, nhưng vẫn bị ngắt sau `...giai đoạn phục` vì chú thích 1 trong PDF hai cột xen vào giữa câu thân bài. |
| L02 | `wb-diemlai-2023-08` p.14 | `chính sách tài khóa nên được thực hiện song hành` | 0 | 2 | 2 | **A** (`p014::c002`, 1399): cụt đầu (`giải ngân đầu tư...`) và cắt giữa từ ở cuối (`làm tăng chênh lệch lãi suấ`) làm mất vế rủi ro tỷ giá của `q06`. **B/C** (`p014::c002`, 1519): trọn câu mở đầu tới hết câu `...gây áp lực cho tỷ giá.`. |
| L03 | `wb-diemlai-2023-08` p.41 | `Những hạn chế về hạ tầng giao thông` | 1 | 1 | 1 | **A** (`c000` 1400 + `c001` 1046): tiêu đề `Hộp 2.1` bị cắt qua 2 chunk; `c001` có mảnh cụt đầu (`họa về...`). **B/C** (`c000` 1343): `by_paragraph` dừng ngay sau dòng tiêu đề `Hộp 2.1. Những hạn chế về hạ tầng giao thông` do giới hạn 1650, để tiêu đề mồ côi khỏi thân hộp ở `c001`. |
| L04 | `wb-diemlai-2023-08` p.48 | `SBIMIS` | 1 | 2 | 2 | **A** (`p048::c001`, 1400): mở đầu cụt từ mục trước và cắt giữa từ cuối chunk (`hệ thống riêng c`). **B/C** (`p048::c001`, 1452): giữ trọn toàn bộ bullet `z Khâu theo dõi và đánh giá hậu kiểm dự án:`. |
| L05 | `wb-diemlai-2024-08` p.15 | `Ngân hàng Thương mại Cổ phần Sài Gòn (SCB)` | 1 | 2 | 2 | **A** (`p015::c001`, 1399): mở đầu bằng đoạn cụt `thấp hơn so với...`, kết thúc cắt dở `Tuy nhiên, lượng`. **B/C** (`p015::c001`, 1053): đúng trọn một đoạn phân tích nợ xấu SCB (4,6%) và VAMC (7,9%). |
| L06 | `wb-diemlai-2024-08` p.28 | `làm dòng vốn ròng phi chính thức ra nước ngoài tăng lên` | 1 | 2 | 2 | **A** (`p028::c000`, 1400): ~680 ký tự đầu lẫn chữ biểu đồ Hình 1.18–1.19, cuối cắt tại dấu phẩy `cuối tháng 3/2024,` mất phần vàng và Lỗi & sai sót (7,9% GDP). **B/C** (`p028::c001`, 1269): tách sạch chữ biểu đồ, giữ trọn đoạn lập luận. |
| L07 | `wb-diemlai-2024-08` p.46 | `nhà đầu tư nội ngành về trái phiếu Chính phủ` | 1 | 2 | 2 | **A** (`p046::c000`, 1400): giữ trọn đoạn BHXH nhưng lấn đoạn sau rồi cắt giữa từ `khi nhiều mã t`. **B/C** (`p046::c000`, 1336): dừng sạch sẽ cuối đoạn 1. |
| L08 | `wb-diemlai-2025-09` p.12 | `8,2 triệu VND` | 1 | 1 | 1 | **A** (`p012::c001`, 1399): cắt giữa từ ở hai đầu (`c trong năm 2025.`, `đóng`). **B/C** (`p012::c000`, 1636): chú thích 2 trong PDF xen giữa `8,2 triệu VND (316` và `US$)` khiến câu bị tách khỏi phần tỷ lệ tiết kiệm 37,2% sang `c001`. |
| L09 | `wb-diemlai-2025-09` p.59 | `ba cụm ĐMST quốc gia` | 1 | 2 | 2 | **A** (`p059::c001`, 1399): đọc đúng thứ tự cột nhưng cắt đầu chunk (`động cao là rào cản...`) và cắt giữa từ câu kết ba cụm ĐMST (`sự gắn kết gi`). **B/C** (`p059::c001`, 1480): trọn chú thích Hình 2.13 và đoạn ba cụm ĐMST (đoạn kế tiếp dừng theo cuối trang 59). |
| L10 | `wb-diemlai-2025-09` p.66 | `từ phòng thí nghiệm đến nhà máy` | 1 | 2 | 2 | **A** (`p066::c000`, 1400): giữ được 2 đoạn vi mạch đầu rồi cắt giữa từ đoạn sinh học (`trong khi c`). **B/C** (`p066::c000`, 1169): dừng tròn ý cuối đoạn phòng sạch vi mạch bán dẫn. |

**Tổng hợp Coherence (`n = 10`):**
- **Strategy A:** Phân bố `0: 1 | 1: 9 | 2: 0` — Trung bình **0,90 / 2** (`9/20`).
- **Strategy B:** Phân bố `0: 0 | 1: 3 | 2: 7` — Trung bình **1,70 / 2** (`17/20`).
- **Strategy C:** Phân bố `0: 0 | 1: 3 | 2: 7` — Trung bình **1,70 / 2** (`17/20`).

---

## 2. Metadata Usefulness (5 câu test × Top-3 = 15 bản ghi / chiến lược)

- **Kiểm tra đủ & đúng (`document_id`, `source`, `page`, `year`, `edition`, `language`, `doc_title`, `section`, `section_title`, `chunking`, `chunk_index`, `char_len`):**
  - **A:** **15/15 (100%)** khớp hoàn toàn với `data/manifest.json` và độ dài `text` thực tế (có thêm `char_start`, `char_end`).
  - **B:** **15/15 (100%)** khớp hoàn toàn.
  - **C:** **15/15 (100%)** khớp hoàn toàn.
- **Filter compliance (`n/N`):**
  - **A:** `N/A` (không áp dụng filter; thực tế không lọc khiến `q19` kéo nhầm năm 2025 ở rank 3 + Chương 1 ở rank 1, và `q20` kéo 2 chunk năm 2024 ở rank 2–3).
  - **B:** `N/A` (không áp dụng filter; thực tế không lọc khiến `q19` xếp `2024-08 p.30` [sai section] ở rank 1 và `2025-09 p.28` [sai năm] ở rank 2; `q20` xếp 2 chunk năm 2024 ở rank 1–2 và đẩy chunk 2025 đúng xuống rank 3).
  - **C:** **2/2 (100%)** trên tập `test` (`q19`, `q20`) và **3/3 (100%)** trên tập `dev` (`q13`, `q14`, `q15`) — mọi chunk top-3 đều tuân thủ `year`/`section`.
- **Trường hữu dụng tiêu biểu:** `year` và `section` loại bỏ hoàn toàn nhiễu xuyên năm/xuyên chương trên chuỗi báo cáo thường niên trùng chủ đề (`q15`, `q19`, `q20`), nâng `Hit@1` của `C` từ `3/5` (`B` test) lên `5/5`. `source` + `page` giúp truy ngược trang PDF vật lý tức thời.
- **Hạn chế metadata:** `section` chỉ phân rã thô ở 3 mức (`tong_luoc`, `kinh_te_vi_mo`, `chuyen_de`), chưa tách được chủ đề con trong cùng chương hay nhãn `box`/`chart`; và Strategy C giả định filter được cung cấp sẵn từ ngữ cảnh truy vấn trước khi tìm kiếm (`WHERE`), chưa có bộ phân tích filter tự động hay cơ chế nới lỏng nếu người dùng nhập sai `section`.

---

## 3. Grounding Quality (5 câu test `q16`–`q20` × Top-3)

Chỉ đánh giá bằng chứng truy xuất (evidence retrieval) để trả lời & truy nguồn; không chấm câu trả lời sinh bởi LLM. Thang điểm: `0` = không có bằng chứng; `1` = thiếu ngữ cảnh/cắt ý/nhiễu niên độ; `2` = đủ trả lời và truy nguồn sạch sẽ.

| Câu | Loại | Gold | A | B | C | Lý do chấm từng chiến lược |
|---|---|---|---:|---:|---:|---|
| `q16` | `direct` | `2023-08` p.53 (alt p.17) | 1 | 2 | 2 | **A:** Rank 1 (`p017::c002`, 0.758) cắt mất câu mở đầu trụ cột 1 (`chất lượng đầu vào/chuẩn bị dự án`) và cụt chữ `về hạc`; Rank 2 (`p053::c000`) cũng thiếu đầu trụ cột 1 và cụt `từng bướ`. **B/C:** Rank 1 (`p017::c002`, 0.744) đủ trọn cả 3 trụ cột từ `chuẩn bị dự án` đến `tài sản công`, Rank 2 hoàn chỉnh trang 53. |
| `q17` | `paraphrased` | `2024-08` p.49 | 2 | 2 | 2 | **A:** Tuy Rank 1 (`p049::c001`, 0.789) bị cắt mất đầu đoạn (`1.632 doanh nghiệp...`), Rank 2 (`p049::c000`, 0.745) chứa phần mở đầu nên hợp top-3 đủ bằng chứng cung-cầu và trang p.49. **B/C:** Rank 1 (`p049::c001`, 0.802) chứa trọn đoạn nguyên vẹn trong 1 chunk. |
| `q18` | `conditional_exception` | `2025-09` p.66 | 2 | 2 | 2 | **A:** Rank 1 (`p066::c000`, 0.836) đủ trọn 2 đoạn nguyên mẫu gửi Đài Loan/Hàn Quốc (6–10 tháng) và thiếu phòng sạch (chỉ dư đuôi cụt đoạn sinh học). **B/C:** Rank 1 (`p066::c000`, 0.847) sạch sẽ đúng 2 đoạn bán dẫn. |
| `q19` | `metadata_filter` | `2024-08` p.15 (`tong_luoc`) | 1 | 1 | 2 | **A & B:** Dù `2024-08` p.15 có mặt ở Rank 2 (**A**) / Rank 3 (**B**), không lọc khiến **A/B** xếp `2024-08` p.30 (Chương 1, có lỗi in gốc `trong năm 2025`) và `2025-09` p.28 (CPI 2025) lên trên/xen vào top-3, gây nhiễu phạm vi. **C:** Filter `{year: 2024, section: 'tong_luoc'}` đưa đúng p.15 lên Rank 1 và chỉ giữ bối cảnh `2024-08` Tóm lược ở Rank 2–3. |
| `q20` | `metadata_filter` | `2025-09` p.34 | 1 | 1 | 2 | **A:** Rank 1 đúng `2025-09` p.34 (hạ 3,1%, rút 1 tỷ US$, còn 78,1 tỷ US$), nhưng Rank 2 & Rank 3 đều là số liệu **năm 2024** (`2024-08` p.14 và p.28: hạ 1,2%, 90 -> 83–84 tỷ US$). **B:** Thậm chí xếp cả 2 chunk năm **2024** ở Rank 1–2, đẩy chunk năm 2025 xuống tận Rank 3. **C:** Filter `{year: 2025}` loại sạch nhiễu 2024, giữ toàn bộ top-3 thuộc 2025 (`p.34`, `p.33`, `p.31`). |

**Tổng hợp Grounding (`n = 5` câu test):**
- **Strategy A:** `0: 0 | 1: 3 | 2: 2` — Trung bình **1,40 / 2** (`7/10`).
- **Strategy B:** `0: 0 | 1: 2 | 2: 3` — Trung bình **1,60 / 2** (`8/10`).
- **Strategy C:** `0: 0 | 1: 0 | 2: 5` — Trung bình **2,00 / 2** (`10/10`).
