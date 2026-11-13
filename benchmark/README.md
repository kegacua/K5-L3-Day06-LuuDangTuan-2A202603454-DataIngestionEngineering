# Benchmark Thiết kế & Quy tắc Khoá trước Khi Chạy Truy hồi

## 1. Cấu trúc Benchmark (`benchmark/questions.json`)

- **Tổng số câu hỏi**: 20 câu hỏi tiếng Việt hoàn toàn độc lập, chia cố định thành **15 câu `dev` (`q01`–`q15`)** và **5 câu `test` (`q16`–`q20`)**.
- **Độ phủ corpus**: Bao phủ cả 3 báo cáo *Điểm lại* của Ngân hàng Thế giới (`wb-diemlai-2023-08`, `wb-diemlai-2024-08`, `wb-diemlai-2025-09`) và cả 3 phân vùng cấu trúc (`tong_luoc`, `kinh_te_vi_mo`, `chuyen_de`).
- **Phân loại câu hỏi**:
  - `direct`: Tra cứu trực tiếp số liệu, cơ chế hoặc khuyến nghị cụ thể.
  - `paraphrased`: Diễn đạt lại khái niệm/nguyên nhân–hệ quả khác với từ ngữ nguyên văn trong tài liệu.
  - `conditional_exception`: Câu hỏi về điều kiện áp dụng, ngoại lệ, cảnh báo hoặc rào cản.
  - `metadata_filter`: **5 câu hỏi** (`q13`–`q15` trong `dev`; `q19`–`q20` trong `test`), trong đó nội dung câu hỏi **không nêu tên năm báo cáo hay mã tài liệu** nhằm mô phỏng truy vấn tự nhiên trong giao diện có bộ lọc ngữ cảnh (`year`, `section`) và kiểm tra khả năng phân giải mơ hồ liên năm của Cấu hình C so với Cấu hình B.
- **Quy tắc chống rò rỉ nhãn**: Không câu hỏi hay bộ lọc nào chứa `gold_source_id` (như `"wb-diemlai-2024-08"`) hoặc `gold_page`; mọi `evidence_quote` (và `alternative_golds` nếu cùng nội dung lặp lại ở `Tổng quan` và `Chương 1`) được kiểm tra khớp nguyên văn trong văn bản đã chuẩn hóa *trước khi chạy truy hồi*.

## 2. Tiêu chí Chọn Cấu hình Khóa Trước (Pre-registered Selection Rule)

Trước khi chạy đánh giá trên `test`, cấu hình thắng cuộc được chọn dựa trên tập `dev` (N = 15) theo thứ tự ưu tiên:
1. **Ưu tiên 1 — Retrieval Accuracy trên `dev`**: Chọn cấu hình có **Evidence Hit@3 trên `dev`** cao nhất (phân xử hòa bằng **Hit@1 trên `dev`**).
2. **Ưu tiên 2 — Tuân thủ bộ lọc metadata**: Với các câu hỏi có gắn bộ lọc cấu trúc (`metadata_filter`), cấu hình dùng bộ lọc phải đạt **100% Filter Compliance** (`n/N` ở cả `dev` và `test`) mà không làm giảm độ chính xác trên nhóm câu hỏi không lọc.
3. **Ưu tiên 3 — Chất lượng đoạn văn bản (Coherence)**: Nếu hai cấu hình có Evidence Hit@3 trên `dev` chênh nhau tối đa 1 câu hỏi (<= 6,7 điểm phần trăm), ưu tiên cấu hình bảo toàn ranh giới đoạn văn/đề mục có điểm trung bình Coherence `/2` cao hơn.

Tập `test` (N = 5) chỉ được chạy **một lần sau khi đã khóa câu hỏi và tiêu chí trên**; không sửa câu hỏi, trích dẫn vàng hay tham số chunking sau khi xem kết quả `test`.

## 3. 10 Vị trí Đánh giá Chunk Coherence Khóa Trước (`benchmark/coherence_locations.json`)

Để so sánh công bằng Cấu hình A (`fixed_size`), B (`by_paragraph`) và C (`by_paragraph + filter`) trên cùng vị trí nguồn (không chọn mẫu tùy tiện sau truy hồi), 10 cặp `(document_id, page, anchor_phrase)` đã được khóa trước gồm `L01`–`L10` trải đều cả 3 tài liệu (4 vị trí năm 2023, 3 vị trí năm 2024, 3 vị trí năm 2025) và đủ các dạng bố cục (2 cột có chú thích, hộp thông tin, danh sách gạch đầu dòng, bảng/hình kèm cột phụ, văn xuôi vĩ mô). Vì B và C dùng chung hoàn toàn bộ chunk, điểm coherence của C bằng B theo thiết kế thí nghiệm có kiểm soát.
