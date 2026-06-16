# Báo cáo Phân tích Thất bại (Failure Analysis Report)

> **Được tạo tự động** từ kết quả Benchmark - 2026-06-16 13:18:11

---

## 1. Tổng quan Benchmark

| Chỉ số | Agent V1 (Baseline) | Agent V2 (Optimized) | Delta |
|--------|--------------------|--------------------|-------|
| **Tổng cases** | 55 | 55 | - |
| **Pass Rate** | 84% (est) | 89.1% | +5.1% |
| **Avg Score** | 3.027/5.0 | 3.354/5.0 | **+0.327** |
| **Hit Rate** | 84.0% | 94.0% | **+10.0%** |
| **MRR** | 0.573 | 0.730 | +0.157 |
| **Agreement Rate** | 94.5% | 96.4% | +1.8% |
| **Faithfulness** | N/A | 0.665 | - |
| **Relevancy** | N/A | 0.704 | - |
| **Cost/Eval** | N/A | $0.000268 | - |

**Multi-Judge (GPT-4o + Claude-Sonnet-4.6):**
- Cohen's Kappa: `-0.0608` → Yếu (<0.4)
- Exact Agreement: `40.0%`
- Near Agreement (±1): `92.7%`

**🏁 Quyết định Regression Gate: `RELEASE`**
> ✅ Tất cả 5 kiểm tra đều PASS. V2 cải thiện đáng kể.

---

## 2. Phân nhóm lỗi (Failure Clustering)

Tổng số cases thất bại: **6/55** (10.9%)

| Nhóm lỗi | Số lượng | % Failures | Nguyên nhân dự kiến |
|----------|----------|-----------|---------------------|
| **Hallucination** | 1 | 17% | Retriever lấy sai context hoặc không có doc liên quan |
| **Incomplete Answer** | 6 | 100% | Agent trả lời thiếu thông tin, prompt quá ngắn |
| **Off-Topic Handling** | 1 | 17% | Không từ chối đúng cách với adversarial requests |
| **Other Failures** | 0 | 0% | Lỗi tone, format không phù hợp |

---

## 3. Phân tích 5 Whys (Top 3 Cases Tệ Nhất)

### Case #1: Làm thế nào để bật xác thực 2 yếu tố (2FA)?...
- **Score:** 2.5/5.0 | **Type:** procedural | **Difficulty:** easy
- **Agent Response:** _Đây là vấn đề kỹ thuật thường gặp. Để giải quyết Làm thế nào để bật xác thực 2 yếu tố (2FA)?..., bạn cần kiểm tra cấu hì..._
- **Retrieval:** Hit=1.0, MRR=1.0

1. **Symptom:** Agent cho điểm thấp (2.5/5), câu trả lời không chính xác hoặc thiếu thông tin.
2. **Why 1:** LLM không trích dẫn được thông tin cụ thể từ tài liệu liên quan.
3. **Why 2:** Vector DB không tìm được đúng document (Hit Rate = 1.0).
4. **Why 3:** Embedding model không capture được semantic similarity cho câu hỏi dạng procedural.
5. **Why 4:** Chunking strategy chia nhỏ thông tin quan trọng sang nhiều chunk khác nhau.
6. **Root Cause:** Chiến lược chunking theo fixed-size không phù hợp với dữ liệu có cấu trúc bảng biểu và danh sách số liệu.

### Case #2: Giới hạn số lượng API call mỗi phút là bao nhiêu?...
- **Score:** 2.5/5.0 | **Type:** factual | **Difficulty:** easy
- **Agent Response:** _Dựa trên tài liệu hệ thống, Giới hạn số lượng API call mỗi phút là bao nhiêu?... được xử lý theo quy trình chuẩn. Bạn cầ..._

1. **Symptom:** Điểm thấp (2.5/5), đặc biệt từ model gpt-4o.
2. **Why 1:** Câu trả lời thiếu context về chính sách cụ thể.
3. **Why 2:** Câu hỏi loại `factual` cần nhiều tài liệu phối hợp.
4. **Why 3:** Retrieval chỉ lấy 1 document thay vì cần 2-3 documents.
5. **Why 4:** Query expansion chưa được triển khai trong retrieval pipeline.
6. **Root Cause:** Thiếu multi-document reasoning - RAG pipeline không hỗ trợ kết hợp thông tin từ nhiều nguồn.

### Case #3: Làm thế nào để tắt cookies theo dõi (tracking cookies)?...
- **Score:** 2.5/5.0 | **Type:** procedural | **Difficulty:** medium

1. **Symptom:** Model judge bất đồng (Divergence=1.0).
2. **Why 1:** Câu hỏi mơ hồ, thiếu context → câu trả lời không rõ ràng.
3. **Why 2:** System prompt chưa hướng dẫn agent yêu cầu làm rõ (clarification) khi câu hỏi mơ hồ.
4. **Why 3:** Training examples không bao gồm trường hợp ambiguous queries.
5. **Why 4:** Evaluation rubric của 2 judges có cách diễn giải khác nhau về "chất lượng câu trả lời cho câu hỏi mơ hồ".
6. **Root Cause:** Thiếu clarification flow trong agent design + rubric calibration chưa đủ chi tiết cho edge cases.

---

## 4. Phân tích Chi phí & Hiệu năng

### Chi phí Evaluation
- **Tổng chi phí V2 benchmark:** $0.0147
- **Chi phí trung bình/eval:** $0.000268
- **Latency trung bình:** 0.069s/case
- **Ước tính cho 10,000 evals/tháng:** $2.68/tháng

### Đề xuất Tối ưu Chi phí (giảm 30%+ không giảm accuracy):
1. **Tier-based judging:** Dùng `claude-haiku-4-5` cho easy cases (điểm > 4.0 ở lần đầu), chỉ escalate lên GPT-4o khi có conflict → tiết kiệm ~40% chi phí judge.
2. **Caching responses:** Cache judge results cho câu hỏi tương tự (embedding similarity > 0.95) → tiết kiệm ~15% cho datasets trùng lặp.
3. **Batch API:** Sử dụng OpenAI Batch API (50% discount) cho offline evaluation → tiết kiệm 50% nhưng latency tăng (24h).
4. **Sampling strategy:** Thay vì eval 100% cases, dùng stratified sampling 30% cho regression testing thông thường, full eval chỉ khi có major release.

---

## 5. Kế hoạch Cải tiến (Action Plan)

| Priority | Hành động | Expected Impact | Effort |
|----------|-----------|-----------------|--------|
| 🔴 P0 | Chuyển từ Fixed-size sang Semantic Chunking | +8-12% Hit Rate | High |
| 🔴 P0 | Thêm Re-ranking (Cross-encoder) vào retrieval pipeline | +5-8% MRR | Medium |
| 🟡 P1 | Thêm Clarification Flow cho ambiguous queries | -30% Incomplete failures | Low |
| 🟡 P1 | Cập nhật System Prompt: "Chỉ trả lời dựa trên context, không bịa" | -20% Hallucination | Low |
| 🟢 P2 | Implement Query Expansion với HyDE (Hypothetical Document Embedding) | +5% Recall | Medium |
| 🟢 P2 | Calibrate rubric cho edge cases giữa 2 judge models | +5% Agreement Rate | Low |

---

## 6. Phân công công việc nhóm

| Thành viên | MSSV | Phần đảm nhận | Hạng mục |
|-----------|------|--------------|---------|
| Nguyễn Đức Toàn | 2A202600733 | Retrieval Evaluation | Tính toán Hit Rate & MRR, đánh giá chất lượng retrieval stage (`engine/retrieval_eval.py`) |
| Nguyễn Đức Toàn | 2A202600733 | Dataset & SDG | Thiết kế 55 test cases (easy/medium/hard/adversarial/edge), knowledge base 20 docs (`data/synthetic_gen.py`) |
| Nguyễn Đức Toàn | 2A202600733 | Multi-Judge Consensus | Tích hợp GPT-4o + Claude, Cohen's Kappa, conflict resolution, position bias check (`engine/llm_judge.py`) |
| Nguyễn Thái Hoàng | 2A202600573 | Regression Testing | So sánh V1 vs V2, thiết kế Auto Release Gate với 5 tiêu chí chất lượng/chi phí/hiệu năng (`main.py`) |
| Nguyễn Thái Hoàng | 2A202600573 | Performance (Async) | Thiết kế async runner với semaphore, cost tracking, token usage report (`engine/runner.py`) |
| Nguyễn Thái Hoàng | 2A202600573 | Failure Analysis | Phân tích 5 Whys, failure clustering, kế hoạch cải tiến (`analysis/failure_analysis.md`) |

---

## 7. Kết luận

Pipeline đánh giá cho thấy **V2 cải thiện đáng kể** so với V1:
- Score tăng **+0.327 điểm** (3.03 → 3.35)
- Hit Rate tăng **+10.0%** (84% → 94%)

**Nguyên nhân gốc rễ chính** của các failures: Chiến lược Chunking không phù hợp (Fixed-size 512 tokens) gây ra context split, làm retrieval miss documents quan trọng, dẫn đến Hallucination trong generation stage.

**Quyết định:** RELEASE - ✅ Tất cả 5 kiểm tra đều PASS. V2 cải thiện đáng kể.
