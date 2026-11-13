# Báo cáo cá nhân — Day 06 · Data Ingestion Engineering

- **Họ và tên:** Lưu Đăng Tuấn
- **MSSV:** `2A202603454` · **Lớp:** `L3A`
- **Repository nộp bài:** <https://github.com/kegacua/K5-L3-Day06-LuuDangTuan-2A202603454-DataIngestionEngineering>

---

## 1. Dữ liệu và pipeline

### 1.1. Chủ đề, nguồn/quyền, số trang và quy tắc tính trang
- **Chủ đề:** Kinh tế vĩ mô, chính sách tài khóa – tiền tệ, đầu tư công, thị trường vốn và phát triển nhân lực công nghệ cao tại Việt Nam qua chuỗi **Báo cáo Điểm lại (*Taking Stock*)** tiếng Việt của **Ngân hàng Thế giới (World Bank)** giai đoạn 2023–2025.
- **Giấy phép & quyền tái sử dụng:** Toàn bộ 3 ấn phẩm phát hành công khai trên World Bank Open Knowledge Repository / Documents & Reports theo giấy phép **Creative Commons Attribution–NonCommercial 3.0 IGO (`CC BY-NC 3.0 IGO`)** (`Public Disclosure Authorized`, mục đích giáo dục/phi thương mại, trích nguồn đầy đủ trong [data/manifest.json](../../data/manifest.json)). Không chứa dữ liệu cá nhân hay tài liệu mật.
- **Quy tắc tính trang hợp lệ:** Đếm theo **số trang PDF vật lý (1-indexed)** chứa nội dung phân tích chính thức (`Tổng quan / Tóm lược`, `Chương 1`, `Chương 2` và phần phụ lục nội dung thuộc báo cáo); loại bỏ các trang bìa trước/sau, trang trống (`0` ký tự trích xuất), trang bản quyền & miễn trừ trách nhiệm, mục lục, danh mục hình/bảng/từ viết tắt, lời cảm ơn, trang ngăn mục chỉ có tiêu đề chương và trang tài liệu tham khảo (`THAM KHẢO`).

| `source_id` | Tên ấn phẩm | Năm / Kỳ | Ngày truy cập & SHA256 (12 ký tự đầu) | Trang vật lý | Trang hợp lệ (`included`) | Loại phi nội dung | Trang trống (`0` char) | Lỗi | URL nguồn chính thức |
|---|---|---|---:|---:|---:|---:|---:|---:|---|
| `wb-diemlai-2023-08` | *Báo cáo Điểm lại, tháng 8/2023: Để đầu tư công thúc đẩy tăng trưởng* | 2023 (`2023-08`) | `2026-11-13` · `32B55097424C` | 58 | **41** | 15 | 2 | 0 | <https://documents1.worldbank.org/curated/en/099417508092322367/pdf/IDU0f9738bf205db7048cc08865045b2bb639b10.pdf> |
| `wb-diemlai-2024-08` | *Báo cáo Điểm lại, tháng 8/2024: Vươn tới tầm cao mới trên thị trường vốn* | 2024 (`2024-08`) | `2026-11-13` · `3B4CEE8A69F8` | 64 | **47** | 14 | 3 | 0 | <https://documents1.worldbank.org/curated/en/099152108232435513/pdf/IDU100472f8411adf1466c1968819d150a0879da.pdf> |
| `wb-diemlai-2025-09` | *Điểm lại tháng 9/2025: Cập nhật tình hình kinh tế Việt Nam — Chuyên đề: Bứt tốc phát triển nhân tài công nghệ cao của Việt Nam* | 2025 (`2025-09`) | `2026-11-13` · `50A3DE0D569F` | 74 | **59** | 12 | 3 | 0 | <https://openknowledge.worldbank.org/bitstreams/37d2b601-35f0-4aee-a4f4-aca47dc95481/download> |
| **Tổng corpus** | **3 báo cáo WB tiếng Việt (2023–2025)** | **2023–2025** | — | **196** | **147** (424.139 ký tự chuẩn hóa) | **41** | **8** | **0** | Log đầy đủ tại [results/ingestion_log.json](../../results/ingestion_log.json) |

### 1.2. Đọc tài liệu, chuẩn hóa, xử lý hai cột, lỗi và giới hạn
- **Công cụ trích xuất:** Python dùng [`pypdf==6.21.4`](../../starter/requirements.txt) với visitor thu thập tọa độ span văn bản (`_extract_page_layout_text` trong [starter/src/ingestion.py](../../starter/src/ingestion.py)).
- **Chuẩn hóa văn bản (`normalize_text` & `_merge_spans_into_lines`):** Chuẩn hóa Unicode `NFC`, tách các ký tự ligature (`ﬀ`, `ﬁ`, `ﬂ`, `ﬃ`, `ﬄ`), chuyển khoảng trắng không ngắt `\u00a0` thành dấu cách và xóa ký tự ẩn (`\u200b`, `\ufeff`), gộp khoảng trắng thừa trong từng đoạn trong khi giữ ranh giới đoạn `\n\n`; đồng thời `_is_running_header_footer` loại bỏ banner header/footer và số trang lặp lại ở vùng mép trên/dưới (`y > 730` hoặc `y < 45`).
- **Khắc phục lỗi đọc hai cột đối xứng (Adaptive Two-Column Detection):** Trong quá trình kiểm tra thô các trang chẵn của `wb-diemlai-2025-09` (ví dụ P12, P14, P16) và trang có cột phụ P59, ngưỡng chia cột cứng ban đầu bị lệch làm chữ cột trái–phải trộn xen kẽ theo dòng. Hàm `_detect_two_column_split(spans)` phân tích các span thân bài (`y` trong `[50, 730]`), phát hiện điểm phân tách cột trái/phải thực tế (`best_rx - 15.0`) kèm điều kiện kiểm tra bảng (`mean_right_len >= 22.0`) để đọc hết cột trái rồi mới sang cột phải thay vì cắt ngang bảng số liệu.
- **Lỗi và giới hạn đã quan sát:**
  1. **Trộn chú thích chân cột giữa câu (PDF layout):** Ở một số trang hai cột có footnote ngắn chen vào vùng tọa độ y phía dưới cột trái (ví dụ `L01` `2023-08` p.11 và `L08` `2025-09` p.12), block footnote lọt vào giữa câu thân bài (giữa `(316` và `US$)` ở `L08`, hoặc sau `...giai đoạn phục` ở `L01`).
  2. **Nhãn trục biểu đồ và bảng lẫn vào văn bản:** Chữ trong các hình biểu đồ vector (như Hình 1.5–1.6 ở `2023-08` p.22, Hình 1.18–1.19 ở `2024-08` p.28, Hình 2.3 ở `2023-08` p.41) vẫn được trích xuất thành dòng ngắn chứa chuỗi số/tên trục gây nhiễu tỷ trọng ngữ nghĩa ở chunk đầu trang.
  3. **Lỗi chính tả/in ấn có sẵn trong PDF gốc & ranh giới trang:** Văn bản nguồn đôi chỗ có lỗi in sẵn (như `đườngoc sắt` ở `2023-08` p.41, `tiết kiệmtăng` ở `2025-09` p.12, và lỗi ghi `"42.400 lợn bị nhiễm trong năm 2025"` ngay trong báo cáo phát hành tháng 8/2024 trang 30); đồng thời pipeline chia chunk độc lập trong phạm vi từng trang nên câu bắc cầu qua cuối trang bị ngắt theo ranh giới trang (`L09` `2025-09` p.59 kết thúc ở `đội ngũ nhân tài nghiên cứu`).
  4. **Trạng thái lỗi đọc:** `0` lỗi ngoại lệ trên toàn bộ `196` trang (`8` trang trống `0` ký tự được ghi log `empty_no_text`, `41` trang phi nội dung ghi log `excluded_non_content`).

### 1.3. Embedding model, vector store, metric, tái nạp không trùng và chi phí
- **Embedding model:** Google Gemini API qua SDK `google-genai==3.3.0`, model **`gemini-embedding-001`**, **768 chiều**, vector chuẩn hóa L2 (`l2_normalized: true`). Tài liệu và truy vấn dùng hai phương thức tách biệt tương thích (`embed_documents` cho chunk và `embed_queries` cho câu hỏi trong [starter/src/embeddings.py](../../starter/src/embeddings.py)). Không sử dụng vector giả/mock; Strategy B và C chia sẻ chính xác cùng tập chunk và vector sinh từ một lần embed.
- **Vector store & metric:** **PostgreSQL `16.16 (Debian 16.16-1.pgdg12+1)`** + **`pgvector 0.8.7`** chạy qua Docker (`pgvector/pgvector:0.8.7-pg16`, cổng `127.0.0.1:55433`, kết nối bằng `psycopg==3.3.8`), bảng lưu bền vững `document_chunks` với khóa chính `(strategy, chunk_id)`, các cột metadata định kiểu có B-tree index (`year`, `section`, `edition`, `document_id`, `source`, `page`, `language`) và cột `metadata JSONB` (kèm GIN index). Truy xuất dùng **exact cosine distance (`<=>`)**; chiến lược C dùng pre-filter SQL `WHERE` có tham số hóa trên các cột định kiểu (chi tiết DDL và truy vấn tại [starter/src/store.py](../../starter/src/store.py)).
- **Kiểm chứng tái nạp không nhân đôi & dọn chunk cũ (`results/reingestion_check.json`):**
  - `PgVectorStore.upsert` dùng `ON CONFLICT (strategy, chunk_id) DO UPDATE` kèm bước xóa các `chunk_id` cũ thuộc cùng `document_id` không còn xuất hiện trong lần nạp mới, và `prune_missing_documents` dọn tài liệu bị loại khỏi manifest.
  - Kiểm thử tự động trong run thực tế xác nhận: nạp tổng hợp 3 chunk -> nạp lặp giữ nguyên `3` dòng (`deleted_obsolete=0`) -> nạp bản rút gọn `3 -> 2` xóa đúng `1` chunk cũ -> dọn sạch `2` dòng tạm; đồng thời tái nạp nguyên văn tài liệu `wb-diemlai-2023-08` (`122` chunk) trong Chiến lược A giữ nguyên tổng số hàng `391 == 391` (`deleted_obsolete=0`, `passed: true`).
- **Lệnh chạy tái lập & tài nguyên thực tế ([results/embedding_stats.json](../../results/embedding_stats.json)):**
  ```powershell
  docker compose -f starter/docker-compose.yml -p day6_student_starter up -d --wait
  starter\.venv\Scripts\python.exe starter\scripts\check_setup.py
  starter\.venv\Scripts\python.exe starter\tests\test_offline.py
  starter\.venv\Scripts\python.exe -u starter\scripts\run_all.py
  ```
  - **Tổng lượt gọi API & token:** **39 API calls** (`20` calls / `147.698` tokens cho A; `18` calls / `136.044` tokens dùng chung cho B & C; `1` call batched / `885` tokens cho 20 câu hỏi) -> **Tổng cộng `284.627` tokens**.
  - **Thời gian & chi phí:** Thời gian API embed thuần `67,8s`; tổng thời gian chạy toàn pipeline `864,73s` (bao gồm thời gian giãn nhịp cửa sổ trượt trong `GeminiEmbedder` để tuân thủ hạn mức Gemini Free Tier ~100 items/phút, ~30.000 TPM và 1.000 RPD bằng `batch_size=20`, trần 70 items/phút và 25.000 TPM). **Chi phí tiền tệ: `$0.00` (Gemini Free Tier)**.

### 1.4. Metadata bắt buộc, trường bổ sung, nguồn giá trị và lý do chọn
- **Bắt buộc (`document_id`, `source`, `page`):** Truy vết trực tiếp về mã tài liệu, đường dẫn PDF gốc và số trang vật lý 1-based (`0/0` suy đoán).
- **Bổ sung (cùng giá trị xác minh từ PDF + `data/manifest.json`):** `year` (`int`: `2023/2024/2025`), `edition` (`str`: `2023-08`/`2024-08`/`2025-09`), `section` (`str`: `tong_luoc` | `kinh_te_vi_mo` | `chuyen_de` ánh xạ từ mục lục từng báo cáo), `section_title` (`str`), `doc_title` (`str`), `language` (`"vi"`), `chunking` (`str`), `chunk_index` (`int`), `char_len` (`int`), kèm `char_start`/`char_end` riêng ở Chiến lược A.
- **Lý do chọn trường lọc (`year`, `section`):** Chuỗi báo cáo *Điểm lại* lặp lại các chỉ báo vĩ mô giống nhau qua từng năm (lạm phát CPI, can thiệp tỷ giá – dự trữ ngoại hối, doanh số bán lẻ, cân đối ngân sách) và tóm tắt lại nội dung Chương 1 trong phần Tổng quan. Do đó `year` giúp phân tách niên độ, còn `section` giúp tách bản tóm lược khỏi chương phân tích chi tiết.

---

## 2. Cấu hình và benchmark

### 2.1. Ba cấu hình thử nghiệm có kiểm soát (A / B / C)
Các biến **corpus (147 trang)**, **embedding model (`gemini-embedding-001`, 768d)**, **vector store (`pgvector`, exact cosine `<=>`)**, **`top_k = 3`** và **kích thước chunk trung bình (~1.180–1.194 ký tự)** được giữ ngang nhau để đảm bảo so sánh công bằng:

| Cấu hình | Chiến lược chunking | Tham số | Số chunk | Độ dài TB (`mean_chars`) | Trung vị (`median_chars`) | Metadata & Filter | Khác biệt có kiểm soát |
|---|---|---|---:|---:|---:|---|---|
| **A** | `fixed_size` | `size=1400`, `overlap=150` | **391** | `1.178,1` (min 160, max 1400) | `1.399,0` | Đủ metadata, **không lọc** | Baseline cắt theo cửa sổ ký tự cố định |
| **B** | `by_paragraph` | `max_size=1650`, `overlap=0` | **355** | `1.193,6` (min 143, max 1725) | `1.256,0` | Đủ metadata, **không lọc** | **A -> B:** chỉ đổi cách chia chunk giữ ranh giới đoạn văn (`mean_chars` chênh 1,3%) |
| **C** | `by_paragraph + filter` | **Chunk & vector y hệt B** (`355`) | **355** | `1.193,6` | `1.256,0` | Đủ metadata + lọc SQL `WHERE` (`year`/`section`) khi câu hỏi có `filter` | **B -> C:** chỉ bật tầng lọc metadata `year`/`section` |

*(Ghi chú kỹ thuật `chunk_stats.json`: Cả A và B/C đều có `short_under_120 = 0`; giá trị `max = 1725` ở B/C phát sinh ở trang có đoạn đầu cận 1650 ghép thêm phần đuôi `<100` ký tự để tránh tạo mảnh vụn cuối trang theo cài đặt trong [starter/src/chunking.py](../../starter/src/chunking.py)).*

### 2.2. Thiết kế benchmark & kiểm chứng trước khi chạy (`benchmark/`)
- **Phân chia cố định (`benchmark/questions.json`):** `20` câu hỏi tiếng Việt hoàn toàn độc lập, chia trước thành **15 `dev` (`q01`–`q15`)** và **5 `test` (`q16`–`q20`)**, phủ đều 3 năm và 3 phân vùng nội dung.
- **Đa dạng câu hỏi & kiểm tra metadata filter:**
  - Gồm câu `direct`, `paraphrased`, `conditional_exception` và **5 câu `metadata_filter`** (`q13`, `q14`, `q15` trong `dev`; `q19`, `q20` trong `test`).
  - Trong cả 5 câu `metadata_filter`, nội dung text câu hỏi cố ý **không nhắc tới năm hoặc mã tài liệu** (mô phỏng ngữ cảnh giao diện lọc người dùng chọn năm/chương trước khi tìm kiếm), đảm bảo không rò rỉ `gold_source_id` hay `gold_page` vào query hay filter. Các câu không gắn filter được Chiến lược C truy vấn bình đẳng như B.
- **Kiểm chứng evidence trước khi chạy:** Mọi `evidence_quote` và `alternative_golds` (cho các nội dung xuất hiện song song ở Tổng quan và Chương 1) đều được đối chiếu khớp nguyên văn với văn bản sau chuẩn hóa trước lúc chạy retrieval (`0` câu sai nguồn).
- **10 vị trí khóa trước để chấm Coherence (`benchmark/coherence_locations.json`):** `L01`–`L10` gồm cặp `(document_id, page, anchor_phrase)` cố định trước khi truy xuất (4 vị trí năm 2023, 3 năm 2024, 3 năm 2025) để tránh chọn mẫu thiên lệch sau khi xem kết quả.

### 2.3. Tiêu chí chọn chiến lược khóa trước khi xem tập `test`
Theo [benchmark/README.md](../../benchmark/README.md), cấu hình thắng cuộc được quyết định hoàn toàn trên tập `dev` (`n = 15`) theo thứ tự:
1. **Ưu tiên 1:** **Evidence Hit@3 trên `dev`** cao nhất (nếu hòa, xét **Hit@1 trên `dev`**).
2. **Ưu tiên 2:** **Filter Compliance = 100%** trên các câu có filter mà không làm suy giảm độ chính xác nhóm không filter.
3. **Ưu tiên 3:** Nếu chênh lệch Hit@3 `<= 1` câu, ưu tiên cấu hình có **Coherence trung bình `/2`** cao hơn.

Tập `test` (`n = 5`) chỉ được dùng **một lần sau khi chốt cấu hình thắng cuộc C trên `dev`**; không chỉnh lại câu hỏi, gold evidence hay tham số sau khi xem `test`.

---

## 3. Kết quả thực nghiệm

| Strategy | Split | Hit@1 (n/N) | Evidence Hit@3 (n/N) | MRR@3 | Chunk count | Thời gian | Chi phí |
|---|---|---:|---:|---:|---:|---|---|
| **A (`fixed_size`)** | `dev` (N=15) | 10/15 (66,7%) | 13/15 (86,7%) | 0,7667 | 391 | 20 API calls docs (`147.698` tokens) | `$0.00` (Free Tier) |
| **A (`fixed_size`)** | `test` (N=5) | 3/5 (60,0%) | 5/5 (100,0%) | 0,8000 | 391 | Thuần embed A+B/C+Q: `67,8s` API | `$0.00` (Free Tier) |
| **B (`by_paragraph`)** | `dev` (N=15) | 13/15 (86,7%) | 15/15 (100,0%) | 0,9333 | 355 | 18 API calls docs (`136.044` tokens) | `$0.00` (Free Tier) |
| **B (`by_paragraph`)** | `test` (N=5) | 3/5 (60,0%) | 5/5 (100,0%) | 0,7333 | 355 | Tổng toàn pipeline: `864,73s` (gồm nhịp chờ TPM/RPM) | `$0.00` (Free Tier) |
| **C (`by_paragraph + filter`)** | `dev` (N=15) | **14/15 (93,3%)** | **15/15 (100,0%)** | **0,9667** | 355 | Dùng chung vector B (`0` doc calls thêm; `885` tokens cho 20 query) | `$0.00` (Free Tier) |
| **C (`by_paragraph + filter`)** | `test` (N=5) | **5/5 (100,0%)** | **5/5 (100,0%)** | **1,0000** | 355 | Tổng `284.627` tokens / 39 calls toàn thí nghiệm | `$0.00` (Free Tier) |

*(Trên toàn bộ `all` N=20: **A** Hit@1 `13/20 (65,0%)`, Evidence Hit@3 `18/20 (90,0%)`, MRR@3 `0,775`; **B** Hit@1 `16/20 (80,0%)`, Evidence Hit@3 `20/20 (100,0%)`, MRR@3 `0,8833`; **C** Hit@1 `19/20 (95,0%)`, Evidence Hit@3 `20/20 (100,0%)`, MRR@3 `0,975`.)*

| Strategy | Coherence trung bình /2 (n) | Metadata đủ và đúng (n/N) | Filter tuân thủ (n/N hoặc N/A) | Grounding 0/1/2 (số câu) và trung bình /2 |
|---|---|---:|---:|---|
| **A (`fixed_size`)** | **0,90 / 2** (`n=10`: `0:1, 1:9, 2:0`) | **15/15 (100%)** | `N/A` (không áp dụng filter) | `0:0 \| 1:3 \| 2:2` — Trung bình **1,40 / 2** (`n=5` test) |
| **B (`by_paragraph`)** | **1,70 / 2** (`n=10`: `0:0, 1:3, 2:7`) | **15/15 (100%)** | `N/A` (không áp dụng filter) | `0:0 \| 1:2 \| 2:3` — Trung bình **1,60 / 2** (`n=5` test) |
| **C (`by_paragraph + filter`)** | **1,70 / 2** (`n=10`: `0:0, 1:3, 2:7`) | **15/15 (100%)** | **`dev`: 3/3 (100%) · `test`: 2/2 (100%)** | `0:0 \| 1:0 \| 2:5` — Trung bình **2,00 / 2** (`n=5` test) |

- **Đường dẫn trace & nhãn thủ công:**
  - Full trace 20 câu × 3 chiến lược: [results/traces.json](../../results/traces.json) và bảng tóm tắt [results/metrics_summary.json](../../results/metrics_summary.json).
  - Bảng mẫu coherence (10 vị trí khóa trước `L01`–`L10`): [results/coherence_samples.json](../../results/coherence_samples.json).
  - Phiếu kiểm tra top-3 tập test (`q16`–`q20` × 3 chiến lược = 45 bản ghi): [results/test_audit_sheet.json](../../results/test_audit_sheet.json).
  - Toàn bộ nhãn & lý do chấm thủ công từng mẫu: [results/manual_audit.md](../../results/manual_audit.md) và [results/manual_audit.json](../../results/manual_audit.json).

---

## 4. Phân tích và kết luận

### 4.1. Đánh giá sâu 5 khía cạnh & so sánh có kiểm soát A–B và B–C

1. **So sánh A vs B (Ảnh hưởng thuần túy của ranh giới chunking):**
   - Trong khi kích thước trung bình gần như không đổi (`1.178,1` vs `1.193,6` ký tự), **B giảm số chunk từ `391` xuống `355` (`-9,2%`)** và giảm token embed tài liệu từ `147.698` xuống `136.044` (`-7,9%`) vì loại bỏ phần trùng lặp `overlap=150`.
   - Về **Retrieval Accuracy trên `dev`**, **B tăng Evidence Hit@3 từ `13/15 (86,7%)` lên `15/15 (100%)`**, **Hit@1 từ `10/15 (66,7%)` lên `13/15 (86,7%)`**, và **MRR@3 từ `0,7667` lên `0,9333`**. Nguyên nhân cốt lõi: `fixed_size` cắt ngang câu/đoạn chứa mệnh đề bằng chứng (`q06`, `q14`, `q15`, `q17`) và trộn chữ biểu đồ vào chung đoạn phân tích (`q11`), làm loãng vector ngữ nghĩa hoặc không khớp đủ cụm bằng chứng trên 1 chunk.
   - Về **Chunk Coherence (`n=10`)**, **B tăng vọt từ `0,90/2` lên `1,70/2`**. A không đạt điểm `2` nào ở cả 10 vị trí (`0:1, 1:9, 2:0`), thậm chí ở `L02` bị cắt cụt cả đầu lẫn giữa từ (`làm tăng chênh lệch lãi suấ`). Tuy nhiên kiểm tra thủ công vẫn ghi nhận công bằng **3 điểm hạn chế (`1/2`) của B/C**: `L01` (`2023-08` p.11) và `L08` (`2025-09` p.12) bị ngắt câu do footnote hai cột xen giữa thân bài, và `L03` (`2023-08` p.41) để tiêu đề `Hộp 2.1` nằm lại cuối `c000` còn thân hộp sang `c001` vì quy tắc gộp tham lam tới `1650` ký tự.

2. **So sánh B vs C (Ảnh hưởng thuần túy của Metadata Filtering):**
   - B và C dùng chunk và embedding giống hệt nhau; mọi khác biệt chỉ xảy ra trên 5 câu `metadata_filter` (`3 dev + 2 test`).
   - Trên **`dev`**, **C nâng Hit@1 từ `13/15 (86,7%)` lên `14/15 (93,3%)`** (MRR@3 `0,9333 -> 0,9667`) và đạt **Filter Compliance `3/3 (100%)`**. Trên **`test`**, khi dữ liệu 2024 và 2025 cùng nhắc đến lạm phát CPI tháng 6 và điều chỉnh tỷ giá trung tâm/bán dự trữ ngoại hối của NHNN, **B tụt Hit@1 xuống `3/5 (60,0%)`**, trong khi **C đạt `5/5 (100%)` Hit@1**, **Filter Compliance `2/2 (100%)`** và **Grounding `2,00/2` (`5/5` đạt mức 2)**.
   - **Khoảng trống giữa Proxy `Evidence Hit@3` và `Grounding` thủ công:** Trên tập `test`, cả A, B, C đều đạt `5/5 (100%)` trên chỉ số tự động `Evidence Hit@3`, nhưng chấm thủ công Grounding phơi bày rõ khuyết tật mà `Hit@3` bỏ qua:
     - Ở `q16` (`test`), A có `Hit@1=True` (`p017::c002`) nhưng lại cắt mất câu mở đầu về *cải thiện chất lượng đầu vào / chuẩn bị dự án* ở đầu trụ cột 1 và cụt cuối chữ `về hạc` -> **A chỉ đạt Grounding `1/2`**, trong khi **B/C đạt `2/2`**.
     - Ở `q19` và `q20` (`test`), A và B dù chứa bản ghi gold trong top-3 vẫn bị **nhiễu xuyên niên độ/chương ở Rank 1–2** (ví dụ `2025-09` xen vào câu hỏi 2024, hay `2024-08` chiếm Rank 1–2 trước `2025-09` ở Rank 3), dẫn tới **Grounding A/B chỉ đạt `1/2`**, còn **C đạt `2/2`**.

3. **Tính hữu dụng của Metadata (`15/15` test hits mỗi chiến lược):**
   - Cả 3 chiến lược đạt **15/15 (100%)** đủ và đúng các trường truy vết và lọc so với `data/manifest.json` và chiều dài chuỗi thực tế.
   - **Lợi ích nổi bật:** `year` và `section` triệt tiêu hoàn toàn nhầm lẫn giữa các kỳ báo cáo thường niên trùng chủ đề (`q15`, `q19`, `q20`) và tách rạch ròi Tóm lược (`tong_luoc`) khỏi Chương 1 (`kinh_te_vi_mo`).
   - **Hạn chế:** `section` chỉ phân chia thô ở 3 mức, chưa tách được tiểu mục chuyên đề hay phân loại `box`/`chart`; và Chiến lược C đòi hỏi filter phải được người dùng hoặc hệ thống trích xuất cung cấp chính xác *trước khi* truy xuất vì `WHERE` loại cứng ngoài SQL không có fallback.

### 4.2. Các ví dụ lỗi cụ thể đã xác minh từ trace

1. **Ví dụ 1 — Cắt giữa câu làm hỏng `Evidence Hit@3` và `Hit@1` (`q15`, `dev`, `wb-diemlai-2023-08` p.22):**
   - *Nguyên nhân ở A:* Cửa sổ cố định cắt ở vị trí `char_start=1250` tách đoạn tại `"Tăng trưởng doanh số bán lẻ ... giảm còn 10,9%..."` (`p022::c000`) ra khỏi phần `"tháng 1 xuống còn có 6,5%... thu nhập 6,3 triệu đồng"` (`p022::c001`, Rank 1, `score=0,748607`). Kết quả A **rớt `Evidence Hit@3=False`** dù Rank 1 nằm đúng trang 22; hai vị trí còn lại bị các báo cáo 2024 (`p013::c001`) và 2025 (`p012::c000`) chiếm chỗ.
   - *Sửa bởi B và C:* B giữ nguyên đoạn trong `wb-diemlai-2023-08::p022::c001` (`char_len=1.487`), cứu được `Evidence Hit@3=True`, nhưng vẫn thua `2024-08::p013::c001` (`0,781623` vs `0,772464`) ở Rank 1 cho đến khi **C** dùng `filter={"year": 2023, "section": "kinh_te_vi_mo"}` đưa `p022::c001` lên **Rank 1**.

2. **Ví dụ 2 — Bỏ sót hoàn toàn trang gold trong Top-3 do trộn bảng/hình & không lọc năm (`q14`, `dev`, `wb-diemlai-2025-09` p.34):**
   - *Nguyên nhân ở A:* A trả top-3 hoàn toàn sai năm (`2024-08::p032::c001` @ `0,76765`, `2023-08::p032::c000` và `p032::c001`). Ngoài việc thiếu filter `year=2025`, trên `2025-09` p.34 chiến lược A gom phần can thiệp tỷ giá đầu trang với đoạn thặng dư ngân sách 3,9% GDP cuối trang thành 1 chunk lẫn nhãn Hình 1.26–1.27, làm loãng vector ngân sách; B tách sạch đoạn thặng dư ngân sách thành `wb-diemlai-2025-09::p034::c001` (`895` ký tự, Rank 1 @ `0,785489`), và C khóa chặt `year=2025, section=kinh_te_vi_mo`.

3. **Ví dụ 3 — Nhiễu liên niên độ khi không dùng metadata filter ở tập `test` (`q20`, `wb-diemlai-2025-09` p.34; và `q19`, `wb-diemlai-2024-08` p.15):**
   - Ở **`q20`** (hỏi về điều chỉnh tỷ giá trung tâm & rút dự trữ ngoại hối năm `2025`), **B** xếp cả Rank 1 (`2024-08::p014::c002`, `score=0,754917`, nói về giảm `1,2%` và dự trữ `90 -> 83-84 tỷ US$` năm 2024) và Rank 2 (`2024-08::p028::c002`, `score=0,753335`) lên trên bằng chứng đúng của năm 2025 (`2025-09::p034::c000`, Rank 3 @ `0,745823`). Khi bật `filter={"year": 2025}` ở **C**, `2025-09::p034::c000` nhảy thẳng lên **Rank 1**, Rank 2–3 đều cung cấp đúng bối cảnh tỷ giá năm 2025 (`p.33`, `p.31`).

4. **Ví dụ 4 — Cắt cụt biên cụm từ phá vỡ chứng cứ ở `q06` (`dev`) & `q17` (`test`), và ca sai chung của benchmark (`q01`, `dev`):**
   - Ở `q06` (`2023-08` p.14), A Rank 1 (`p014::c003`, `220` ký tự) mở đầu bằng mảnh cụt giữa từ `"uất thêm nữa chưa chắc đã..."`, mất mệnh đề điều kiện đầu câu nên `evidence_match=False` (`Hit@1=False`). Tương tự ở `q17` (`test`, `2024-08` p.49), A Rank 1 (`p049::c001`) cắt mất cụm `"mặc dù có đến 1.632 doanh nghiệp"` ở đầu câu -> `Hit@1=False`, trong khi B/C giữ trọn đoạn đạt Rank 1 (`score=0,801638`).
   - Đáng chú ý ở **`q01`** (`dev`, thiệt hại `0,3% GDP` do thiếu điện miền Bắc 2023), **cả A, B, C đều có `Hit@1=False`** dù câu hỏi khá dễ: cả 3 chiến lược đều xếp **`wb-diemlai-2023-08::p023::c001` (Hộp 1.1 — giải thích chi tiết phí tổn 1,4 tỷ US$ / 0,3% GDP)** ở **Rank 1** (`0,815` ở B/C) trên `p.22` (Rank 2) và `p.11` (Rank 3). Vì bộ benchmark đã khóa `p.22` (và `alt` `p.11`) *trước khi chạy* mà chưa liệt kê `p.23`, giữ nguyên không sửa nhãn giúp phản ánh trung thực **giới hạn chú giải đa nguồn đồng nghĩa** của benchmark thay vì "tô hồng" `Hit@1` hồi tố.

### 4.3. Chiến lược chọn, đánh đổi và điều kiện áp dụng
- **Lựa chọn cuối cùng:** Chọn **Chiến lược C (`by_paragraph`, `max_size=1650`, kết hợp PostgreSQL SQL metadata filter `year`/`section`)** dựa trên tiêu chí khóa trước ở tập `dev` (**Evidence Hit@3 = `15/15`, Hit@1 = `14/15`, Filter Compliance = `3/3`, Coherence = `1,70/2`**) — và được xác nhận hoàn toàn trên `test` (**Hit@1 = `5/5`, Evidence Hit@3 = `5/5`, Filter = `2/2`, Grounding = `2,00/2`**).
- **Đánh đổi & điều kiện áp dụng:**
  - Chọn `by_paragraph` đánh đổi lấy độ mạch lạc cao hơn và giảm ~9% dung lượng vector/token, nhưng đòi hỏi chi phí tiền xử lý cấu trúc văn bản theo từng loại tài liệu (tách cột thích ứng, ngưỡng gộp đoạn) và nhạy cảm hơn với bố cục footnote PDF (`L01`, `L08`) so với cửa sổ trượt đơn giản có `overlap`.
  - Chọn lọc metadata `WHERE` trước truy xuất phát huy tối đa hiệu quả khi corpus gồm **nhiều kỳ báo cáo/phiên bản lặp chủ đề qua các năm** và ứng dụng có sẵn ngữ cảnh lọc (dropdown năm/chương hoặc router phân loại). Ngược lại, với truy vấn mở hoàn toàn không kèm ngữ cảnh hoặc bộ lọc gán nhầm phân vùng, lọc cứng sẽ tạo lỗi bỏ sót (`zero recall`) nếu không có cơ chế fallback.

### 4.4. Hạn chế của thí nghiệm & hướng cải tiến
- **Hạn chế dữ liệu & đo lường:**
  1. Tập `test` nhỏ (`N=5`, trong đó chỉ có 2 câu `metadata_filter`) và `dev` vừa (`N=15`) chỉ mang tính minh họa có kiểm soát cho corpus 3 báo cáo World Bank này; **không khẳng định chiến lược C tối ưu tổng quát** cho mọi miền văn bản khác.
  2. Toàn bộ nhãn Coherence (`L01`–`L10`), Grounding (`q16`–`q20`) và xây dựng câu hỏi đều do **một người thực hiện (tác giả kiêm người chấm)** nên tiềm ẩn thiên lệch đánh giá; đã giảm thiểu bằng việc khóa câu hỏi, vị trí kiểm tra và quy tắc chọn trước khi chạy, đồng thời ghi nhận đủ các lỗi thực tế của B/C.
  3. Thời gian thực thi `864,73s` phản ánh phần lớn độ trễ chờ hạn mức RPM/TPM miễn phí của Gemini API (`embed_seconds = 67,8s` thuần gọi mạng) kết hợp tập dữ liệu 147 trang chưa dùng HNSW index vì kích thước chỉ 355–391 vector phù hợp tìm kiếm chính xác (`exact cosine`).
- **Cải tiến ưu tiên nếu làm lại hoặc mở rộng:**
  1. Tách riêng chú thích chân cột (`footnote`), bảng số liệu (`Bảng x.x`) và trục biểu đồ (`Hình x.x`) ra khỏi luồng đoạn văn chính trước khi `by_paragraph` để khắc phục triệt để lỗi ngắt giữa câu như `L01`, `L08`.
  2. Bổ sung quy tắc **khóa tiêu đề về phía trước (forward-attach heading)**: không kết thúc chunk ngay sau dòng tiêu đề ngắn (như `Hộp 2.1...` ở `L03`) mà đính kèm với đoạn thân tiếp theo.
  3. Mở rộng **Hybrid Retrieval (Dense pgvector + BM25/FTS PostgreSQL `tsvector` + RRF)** và tầng **tự động suy luận bộ lọc mềm / fallback** khi điều kiện `WHERE` trả về ít hơn `top_k` kết quả, đồng thời kiểm định chéo với người chấm độc lập trên tập test lớn hơn (`N >= 30`).

---

## 5. Minh bạch sử dụng AI và tự kiểm chứng (`RULES.md`)
- **Công cụ sử dụng:** Sử dụng trợ lý AI lập trình hỗ trợ viết khung hàm trong `starter/src/` (`ingestion.py`, `chunking.py`, `embeddings.py`, `store.py`, `evaluation.py`, `run.py`), unit test `test_offline.py` và rà soát tài liệu báo cáo.
- **Cách kiểm chứng độc lập của tác giả:**
  - Tự chọn corpus công khai WB *Điểm lại* (2023–2025), đọc xác minh giấy phép `CC BY-NC 3.0 IGO`, khóa danh sách trang hợp lệ trong `data/manifest.json` và tự xây 20 câu hỏi + 10 vị trí coherence trong `benchmark/` trước khi chạy thực nghiệm.
  - Chạy thực nghiệm thật với Docker PostgreSQL 16 + pgvector 0.8.7 (`check_setup.py`) và Google `gemini-embedding-001` (`run_all.py`), chạy kiểm thử offline (`test_offline.py`), và **trực tiếp đọc toàn bộ text từng chunk** trong `coherence_samples.json`, `test_audit_sheet.json` và các ca sai của `traces.json` để chấm thủ công `manual_audit.json` / `manual_audit.md` hoàn toàn theo kết quả thực tế.
