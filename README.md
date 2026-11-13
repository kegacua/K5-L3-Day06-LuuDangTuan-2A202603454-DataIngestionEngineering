# Day 06 · Data Ingestion Engineering (Bài nộp cá nhân — Lưu Đăng Tuấn, 2A202603454)

> Thực hiện thử nghiệm có kiểm soát ba chiến lược chuẩn bị dữ liệu (`A: fixed_size`, `B: by_paragraph`, `C: by_paragraph + SQL metadata filter`) trên **3 báo cáo *Điểm lại* tiếng Việt của Ngân hàng Thế giới (2023–2025)** — **147 trang nội dung hợp lệ**, embedding thật **`gemini-embedding-001` (768 chiều)** và lưu trữ bền vững bằng **PostgreSQL 16.16 + pgvector 0.8.7**.

| 📄 Corpus hợp lệ | 🧩 Chiến lược có kiểm soát | 🎯 Benchmark khóa trước | 🏆 Chiến lược chọn (`dev`) |
|---|---|---|---|
| **147 trang** (424.139 ký tự chuẩn hóa, `CC BY-NC 3.0 IGO`) | **A** (391 chunks) · **B** (355 chunks) · **C** (355 chunks + filter) | **20 câu** (15 `dev` + 5 `test`, 5 câu filter) + 10 vị trí coherence | **C** (`dev` Hit@1 **14/15**, Hit@3 **15/15**, Filter **3/3**) |

---

## 1. Cấu trúc thư mục bài nộp

```text
├── STUDENT.md                                    # Thông tin học viên (Lưu Đăng Tuấn - 2A202603454)
├── data/
│   └── manifest.json                             # Nguồn OKR/WDS, SHA256, CC BY-NC 3.0 IGO, 147/196 trang, section_ranges
├── benchmark/
│   ├── README.md                                 # Thiết kế benchmark & quy tắc chọn chiến lược khóa trước test
│   ├── questions.json                            # 20 câu hỏi (q01-q15 dev, q16-q20 test), evidence_quote & alternative_golds
│   └── coherence_locations.json                  # 10 vị trí L01-L10 khóa trước để chấm coherence 0/1/2
├── starter/
│   ├── docker-compose.yml                        # PostgreSQL 16 + pgvector 0.8.7 (cổng 127.0.0.1:55433)
│   ├── init.sql                                  # CREATE EXTENSION vector
│   ├── requirements.txt                          # psycopg[binary]==3.3.8, pypdf, python-dotenv
│   ├── .env.example                              # Mẫu biến môi trường (copy thành starter/.env, không commit .env)
│   ├── data/                                     # 3 file PDF WB Điểm lại (tải từ source_url trong data/manifest.json)
│   ├── scripts/
│   │   ├── check_setup.py                        # Kiểm tra kết nối Postgres & pgvector
│   │   └── run_all.py                            # Wrapper chạy toàn bộ pipeline từ repo root
│   ├── src/
│   │   ├── ingestion.py                          # Đọc PDF layout span (pypdf), tách 2 cột thích ứng, chuẩn hóa Unicode/ligature
│   │   ├── chunking.py                           # fixed_size(1400, 150) và by_paragraph(max_size=1650)
│   │   ├── embeddings.py                         # GeminiEmbedder (gemini-embedding-001, 768d, Free-Tier RPM/TPM pacing)
│   │   ├── store.py                              # PgVectorStore (document_chunks): upsert idempotent, pruning chunk/tài liệu cũ, SQL metadata filter
│   │   ├── evaluation.py                         # Chấm Hit@1, Evidence Hit@3, page_hit, MRR@3, Filter Compliance
│   │   └── run.py                                # Pipeline end-to-end A/B/C + test tái nạp + xuất trace & sheet audit
│   └── tests/test_offline.py                     # Kiểm thử unit offline cho ingestion, chunking, evaluation, manifest & benchmark
├── artifacts/experiment_log.csv                  # Nhật ký tham số, giả thuyết và kết quả A/B/C
├── results/
│   ├── ingestion_log.json                        # Log từng trang (147 included, 41 excluded_non_content, 8 empty, 0 errors)
│   ├── chunk_stats.json                          # Phân bố độ dài chunk A/B/C
│   ├── embedding_stats.json                      # Token, API calls, thời gian chạy, phiên bản Postgres/pgvector
│   ├── reingestion_check.json                    # Kiểm chứng tái nạp không nhân đôi & dọn chunk cũ
│   ├── metrics_summary.json                      # Chỉ số tổng hợp dev/test/all cho A/B/C
│   ├── traces.json                               # Full trace top-3 toàn bộ 20 câu hỏi × 3 chiến lược
│   ├── coherence_samples.json                    # Chunks khớp 10 vị trí L01-L10 kèm nguyên văn trang nguồn
│   ├── test_audit_sheet.json                     # Phiếu kiểm tra 5 câu test (q16-q20) × top-3 × 3 chiến lược
│   ├── manual_audit.json                         # Nhãn chấm thủ công coherence, metadata và grounding kèm lý do
│   └── manual_audit.md                           # Bảng tổng hợp nhãn thủ công & tuyên bố thiên lệch
└── report/individual/2A202603454_LuuDangTuan.md  # Báo cáo cá nhân hoàn chỉnh theo REPORT_TEMPLATE.md
```

---

## 2. Hướng dẫn cài đặt và tái lập (Reproducibility)

### Yêu cầu môi trường
- Python **3.11+** (đã chạy trên Python 3.11 / Windows; dùng `pypdf==6.21.4`, `psycopg[binary]==3.3.8`, `python-dotenv==1.2.4`, `google-genai==3.3.0`)
- **Docker Engine / Docker Desktop** + Docker Compose v2
- **Gemini API key** (`GEMINI_API_KEY`) để tạo embedding thật qua `gemini-embedding-001` (nếu dùng gói Free Tier ~100 items/phút, ~30.000 TPM, 1.000 RPD; pipeline tự giãn nhịp để không mất dữ liệu).

### Các bước chạy lại từ đầu

1. **Dựng PostgreSQL + pgvector bằng Docker:**
   ```powershell
   docker compose -f starter/docker-compose.yml -p day6_student_starter up -d --wait
   ```

2. **Tạo virtualenv và cài thư viện:**
   ```powershell
   cd starter
   python -m venv .venv
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   .\.venv\Scripts\python.exe -m pip install google-genai==3.3.0
   ```
   *(Linux/macOS thay bằng `source .venv/bin/activate && pip install ...`)*

3. **Cấu hình `starter/.env` (không commit file này):**
   ```powershell
   Copy-Item starter\.env.example starter\.env
   ```
   Điền `GEMINI_API_KEY=<your_api_key>` và giữ cấu hình DB mặc định:
   ```dotenv
   DATABASE_URL=postgresql://day6:day6_local_only@127.0.0.1:55433/day6_lab
   EMBEDDING_MODEL=gemini-embedding-001
   EMBEDDING_DIMENSIONS=768
   ```

4. **Kiểm tra dữ liệu nguồn (`starter/data/`):**
   Đảm bảo 3 file PDF công khai của Ngân hàng Thế giới nằm tại:
   - `starter/data/wb_diemlai_2023_08.pdf`
   - `starter/data/wb_diemlai_2024_08.pdf`
   - `starter/data/wb_diemlai_2025_09.pdf`
   (Xem URL tải chính thức, ngày truy cập `2026-11-13` và SHA256 đối chiếu trong [data/manifest.json](data/manifest.json)).

5. **Kiểm tra hạ tầng DB & unit test offline:**
   ```powershell
   starter\.venv\Scripts\python.exe starter\scripts\check_setup.py
   starter\.venv\Scripts\python.exe starter\tests\test_offline.py
   ```

6. **Chạy toàn bộ pipeline A/B/C:**
   ```powershell
   # Từ thư mục gốc repo:
   starter\.venv\Scripts\python.exe -u starter\scripts\run_all.py
   # Hoặc từ thư mục starter/:
   # cd starter && python -m src.run
   ```

---

## 3. Tóm tắt kết quả thực nghiệm (đã xác minh từ run thật)

| Strategy | Split | Hit@1 (n/N) | Evidence Hit@3 (n/N) | Chunks | Coherence (/2) | Metadata Đủ & Đúng | Filter Compliance | Grounding (/2) |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| **A (`fixed_size`)** | `dev` (n=15) | 10/15 (66.7%) | 13/15 (86.7%) | 391 | 0,90 / 2 (n=10) | — | N/A | — |
| **A (`fixed_size`)** | `test` (n=5) | 3/5 (60.0%) | 5/5 (100.0%) | 391 | 0,90 / 2 (n=10) | 15/15 (100%) | N/A | 1,40 / 2 (n=5) |
| **B (`by_paragraph`)** | `dev` (n=15) | 13/15 (86.7%) | 15/15 (100.0%) | 355 | 1,70 / 2 (n=10) | — | N/A | — |
| **B (`by_paragraph`)** | `test` (n=5) | 3/5 (60.0%) | 5/5 (100.0%) | 355 | 1,70 / 2 (n=10) | 15/15 (100%) | N/A | 1,60 / 2 (n=5) |
| **C (`by_paragraph + filter`)** | `dev` (n=15) | **14/15 (93.3%)** | **15/15 (100.0%)** | 355 | 1,70 / 2 (n=10) | — | **3/3 (100%)** | — |
| **C (`by_paragraph + filter`)** | `test` (n=5) | **5/5 (100.0%)** | **5/5 (100.0%)** | 355 | 1,70 / 2 (n=10) | **15/15 (100%)** | **2/2 (100%)** | **2,00 / 2 (n=5)** |

Chi tiết phân tích đầy đủ 5 khía cạnh, ví dụ lỗi, nhật ký chi phí/thời gian, hạn chế và phương án mở rộng xem tại [report/individual/2A202603454_LuuDangTuan.md](report/individual/2A202603454_LuuDangTuan.md).

---

## Tài liệu hướng dẫn gốc của môn học
- [GUIDE.md](GUIDE.md) · [BENCHMARK.md](BENCHMARK.md) · [RUBRIC.md](RUBRIC.md) · [RULES.md](RULES.md) · [SUBMISSION.md](SUBMISSION.md) · [starter/README.md](starter/README.md)
