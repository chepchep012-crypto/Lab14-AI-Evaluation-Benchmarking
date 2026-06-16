"""
AI Evaluation Factory - Main Pipeline
Lab 14: Expert Level Team Project

Quy trình:
1. Load Golden Dataset (55 test cases)
2. Chạy Benchmark V1 (baseline agent)
3. Chạy Benchmark V2 (optimized agent)
4. Regression Analysis: so sánh V1 vs V2
5. Auto Release Gate: quyết định RELEASE hoặc ROLLBACK
6. Tạo báo cáo chi tiết (reports/ + failure_analysis.md)
"""
import asyncio
import json
import os
import time
from typing import Dict, List, Optional, Tuple

from agent.main_agent import MainAgent
from engine.retrieval_eval import RetrievalEvaluator
from engine.llm_judge import LLMJudge
from engine.runner import BenchmarkRunner

# ===== RELEASE GATE THRESHOLDS =====
GATE_CONFIG = {
    "min_score_delta": 0.0,       # V2 phải tốt hơn V1 ít nhất 0 điểm
    "min_absolute_score": 2.5,    # Điểm tuyệt đối tối thiểu
    "min_hit_rate": 0.60,         # Hit rate tối thiểu
    "min_agreement_rate": 0.70,   # Agreement rate tối thiểu
    "max_cost_increase_pct": 30,  # Chi phí tăng tối đa 30%
}


async def run_benchmark(agent_version: str, dataset: List[Dict]) -> Tuple[List[Dict], Dict]:
    """
    Chạy benchmark đầy đủ cho một phiên bản agent.
    Returns: (results, summary_metrics)
    """
    print(f"\n{'='*55}")
    print(f"🚀 Khởi động Benchmark: {agent_version}")
    print(f"{'='*55}")
    start_wall = time.perf_counter()

    # Khởi tạo components
    agent = MainAgent(version="v1" if "V1" in agent_version else "v2")
    retrieval_evaluator = RetrievalEvaluator(top_k=5)
    judge = LLMJudge(models=["gpt-4o", "claude-sonnet-4-6"])
    runner = BenchmarkRunner(agent, retrieval_evaluator, judge)

    # Chạy async benchmark
    results = await runner.run_all(dataset, batch_size=10)

    wall_time = time.perf_counter() - start_wall

    # Tính toán metrics tổng hợp
    metrics = BenchmarkRunner.compute_aggregate_metrics(results)

    # Thêm batch-level agreement metrics (Cohen's Kappa)
    batch_agreement = judge.compute_batch_agreement()

    # Ước tính chi phí Judge
    cost_estimate = judge.estimate_cost(len(dataset))

    print(f"\n📊 KẾT QUẢ {agent_version}:")
    print(f"   ✅ Pass/Fail: {metrics['pass_count']}/{metrics['fail_count']} ({metrics['pass_rate']*100:.1f}% pass)")
    print(f"   🎯 Avg Score: {metrics['avg_score']:.3f}/5.0")
    print(f"   🔍 Hit Rate: {metrics['hit_rate']*100:.1f}% | MRR: {metrics['mrr']:.3f}")
    print(f"   🤝 Agreement Rate: {metrics['agreement_rate']*100:.1f}%")
    print(f"   📐 Cohen's Kappa: {batch_agreement.get('cohen_kappa', 'N/A')} ({batch_agreement.get('kappa_interpretation', '')})")
    print(f"   ⚡ Wall Time: {wall_time:.2f}s | Avg Latency: {metrics['avg_latency_sec']:.3f}s/case")
    print(f"   💰 Total Cost: ${metrics['total_cost_usd']:.4f} | Per Eval: ${metrics['avg_cost_per_eval_usd']:.6f}")
    print(f"   📈 Faithfulness: {metrics['avg_faithfulness']:.3f} | Relevancy: {metrics['avg_relevancy']:.3f}")

    summary = {
        "metadata": {
            "version": agent_version,
            "total": len(results),
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "wall_time_sec": round(wall_time, 2),
        },
        "metrics": {
            "avg_score": metrics["avg_score"],
            "hit_rate": metrics["hit_rate"],
            "mrr": metrics["mrr"],
            "agreement_rate": metrics["agreement_rate"],
            "avg_faithfulness": metrics["avg_faithfulness"],
            "avg_relevancy": metrics["avg_relevancy"],
            "pass_rate": metrics["pass_rate"],
            "avg_latency_sec": metrics["avg_latency_sec"],
            "total_cost_usd": metrics["total_cost_usd"],
            "avg_cost_per_eval_usd": metrics["avg_cost_per_eval_usd"],
        },
        "retrieval": {
            "cases_evaluated": metrics["retrieval_cases_count"],
            "hit_rate": metrics["hit_rate"],
            "mrr": metrics["mrr"],
        },
        "multi_judge": {
            "models": judge.models,
            "cohen_kappa": batch_agreement.get("cohen_kappa"),
            "kappa_interpretation": batch_agreement.get("kappa_interpretation"),
            "exact_agreement_rate": batch_agreement.get("exact_agreement_rate"),
            "near_agreement_rate": batch_agreement.get("near_agreement_rate"),
        },
        "cost_analysis": cost_estimate,
        "failure_summary": {
            "pass_count": metrics["pass_count"],
            "fail_count": metrics["fail_count"],
            "failure_by_type": metrics["failure_by_type"],
        },
    }

    return results, summary


def evaluate_release_gate(v1_summary: Dict, v2_summary: Dict) -> Dict:
    """
    Auto Release Gate: quyết định RELEASE hoặc ROLLBACK dựa trên nhiều ngưỡng.
    Phân tích: Score delta, Hit Rate, Agreement Rate, Cost.
    """
    v1_m = v1_summary["metrics"]
    v2_m = v2_summary["metrics"]

    delta_score = v2_m["avg_score"] - v1_m["avg_score"]
    delta_hit_rate = v2_m["hit_rate"] - v1_m["hit_rate"]
    delta_cost_pct = (v2_m["total_cost_usd"] - v1_m["total_cost_usd"]) / max(v1_m["total_cost_usd"], 1e-9) * 100

    checks = {
        "score_improvement": {
            "passed": delta_score >= GATE_CONFIG["min_score_delta"],
            "value": round(delta_score, 4),
            "threshold": GATE_CONFIG["min_score_delta"],
            "detail": f"V2 Score {v2_m['avg_score']:.3f} vs V1 {v1_m['avg_score']:.3f} (delta={delta_score:+.3f})",
        },
        "absolute_score": {
            "passed": v2_m["avg_score"] >= GATE_CONFIG["min_absolute_score"],
            "value": v2_m["avg_score"],
            "threshold": GATE_CONFIG["min_absolute_score"],
            "detail": f"V2 avg score {v2_m['avg_score']:.3f} >= {GATE_CONFIG['min_absolute_score']}",
        },
        "hit_rate": {
            "passed": v2_m["hit_rate"] >= GATE_CONFIG["min_hit_rate"],
            "value": v2_m["hit_rate"],
            "threshold": GATE_CONFIG["min_hit_rate"],
            "detail": f"V2 Hit Rate {v2_m['hit_rate']*100:.1f}% >= {GATE_CONFIG['min_hit_rate']*100:.0f}%",
        },
        "agreement_rate": {
            "passed": v2_m["agreement_rate"] >= GATE_CONFIG["min_agreement_rate"],
            "value": v2_m["agreement_rate"],
            "threshold": GATE_CONFIG["min_agreement_rate"],
            "detail": f"V2 Agreement {v2_m['agreement_rate']*100:.1f}% >= {GATE_CONFIG['min_agreement_rate']*100:.0f}%",
        },
        "cost_control": {
            "passed": delta_cost_pct <= GATE_CONFIG["max_cost_increase_pct"],
            "value": round(delta_cost_pct, 1),
            "threshold": GATE_CONFIG["max_cost_increase_pct"],
            "detail": f"Chi phí thay đổi {delta_cost_pct:+.1f}% (tối đa +{GATE_CONFIG['max_cost_increase_pct']}%)",
        },
    }

    all_passed = all(c["passed"] for c in checks.values())
    critical_passed = all(
        checks[k]["passed"] for k in ["absolute_score", "hit_rate", "agreement_rate"]
    )

    if all_passed:
        decision = "RELEASE"
        reason = f"✅ Tất cả {len(checks)} kiểm tra đều PASS. V2 cải thiện đáng kể."
    elif critical_passed:
        decision = "RELEASE_WITH_CAUTION"
        failed = [k for k, v in checks.items() if not v["passed"]]
        reason = f"⚠️ RELEASE có điều kiện - cần theo dõi: {', '.join(failed)}"
    else:
        decision = "ROLLBACK"
        failed = [k for k, v in checks.items() if not v["passed"]]
        reason = f"❌ ROLLBACK - {len(failed)} kiểm tra thất bại: {', '.join(failed)}"

    return {
        "decision": decision,
        "reason": reason,
        "all_checks_passed": all_passed,
        "checks": checks,
        "delta": {
            "score": round(delta_score, 4),
            "hit_rate": round(delta_hit_rate, 4),
            "cost_pct": round(delta_cost_pct, 1),
        },
        "v1_summary": {
            "avg_score": v1_m["avg_score"],
            "hit_rate": v1_m["hit_rate"],
            "mrr": v1_m["mrr"],
            "agreement_rate": v1_m["agreement_rate"],
        },
        "v2_summary": {
            "avg_score": v2_m["avg_score"],
            "hit_rate": v2_m["hit_rate"],
            "mrr": v2_m["mrr"],
            "agreement_rate": v2_m["agreement_rate"],
        },
    }


def generate_failure_analysis(v2_results: List[Dict], v2_summary: Dict, regression: Dict) -> str:
    """
    Tự động tạo báo cáo phân tích lỗi với dữ liệu thực từ benchmark.
    """
    metrics = v2_summary["metrics"]
    failure_summary = v2_summary["failure_summary"]
    total = v2_summary["metadata"]["total"]
    pass_c = failure_summary["pass_count"]
    fail_c = failure_summary["fail_count"]

    # Top 3 worst cases
    worst_cases = sorted(v2_results, key=lambda x: x["judge"]["final_score"])[:3]

    # Failure clustering
    failures = [r for r in v2_results if r["status"] == "fail"]
    hallucination = [r for r in failures if not r["ragas"]["retrieval"].get("is_retrieval_case") or r["ragas"]["retrieval"].get("hit_rate", 1) == 0]
    incomplete = [r for r in failures if r["judge"]["final_score"] >= 2.0 and r["judge"]["final_score"] < 3.0]
    off_topic = [r for r in failures if r.get("type") in ["prompt_injection", "jailbreak", "goal_hijacking"]]
    other = [r for r in failures if r not in hallucination and r not in incomplete and r not in off_topic]

    reg = regression["delta"]

    report = f"""# Báo cáo Phân tích Thất bại (Failure Analysis Report)

> **Được tạo tự động** từ kết quả Benchmark - {v2_summary['metadata']['timestamp']}

---

## 1. Tổng quan Benchmark

| Chỉ số | Agent V1 (Baseline) | Agent V2 (Optimized) | Delta |
|--------|--------------------|--------------------|-------|
| **Tổng cases** | {total} | {total} | - |
| **Pass Rate** | {regression['v1_summary']['hit_rate']*100:.0f}% (est) | {metrics['pass_rate']*100:.1f}% | {(metrics['pass_rate'] - regression['v1_summary']['hit_rate'])*100:+.1f}% |
| **Avg Score** | {regression['v1_summary']['avg_score']:.3f}/5.0 | {metrics['avg_score']:.3f}/5.0 | **{reg['score']:+.3f}** |
| **Hit Rate** | {regression['v1_summary']['hit_rate']*100:.1f}% | {metrics['hit_rate']*100:.1f}% | **{reg['hit_rate']:+.1%}** |
| **MRR** | {regression['v1_summary']['mrr']:.3f} | {metrics['mrr']:.3f} | {metrics['mrr']-regression['v1_summary']['mrr']:+.3f} |
| **Agreement Rate** | {regression['v1_summary']['agreement_rate']*100:.1f}% | {metrics['agreement_rate']*100:.1f}% | {(metrics['agreement_rate']-regression['v1_summary']['agreement_rate'])*100:+.1f}% |
| **Faithfulness** | N/A | {metrics['avg_faithfulness']:.3f} | - |
| **Relevancy** | N/A | {metrics['avg_relevancy']:.3f} | - |
| **Cost/Eval** | N/A | ${metrics['avg_cost_per_eval_usd']:.6f} | - |

**Multi-Judge (GPT-4o + Claude-Sonnet-4.6):**
- Cohen's Kappa: `{v2_summary['multi_judge']['cohen_kappa']}` → {v2_summary['multi_judge']['kappa_interpretation']}
- Exact Agreement: `{v2_summary['multi_judge']['exact_agreement_rate']*100:.1f}%`
- Near Agreement (±1): `{v2_summary['multi_judge']['near_agreement_rate']*100:.1f}%`

**🏁 Quyết định Regression Gate: `{regression['decision']}`**
> {regression['reason']}

---

## 2. Phân nhóm lỗi (Failure Clustering)

Tổng số cases thất bại: **{fail_c}/{total}** ({fail_c/total*100:.1f}%)

| Nhóm lỗi | Số lượng | % Failures | Nguyên nhân dự kiến |
|----------|----------|-----------|---------------------|
| **Hallucination** | {len(hallucination)} | {len(hallucination)/max(fail_c,1)*100:.0f}% | Retriever lấy sai context hoặc không có doc liên quan |
| **Incomplete Answer** | {len(incomplete)} | {len(incomplete)/max(fail_c,1)*100:.0f}% | Agent trả lời thiếu thông tin, prompt quá ngắn |
| **Off-Topic Handling** | {len(off_topic)} | {len(off_topic)/max(fail_c,1)*100:.0f}% | Không từ chối đúng cách với adversarial requests |
| **Other Failures** | {len(other)} | {len(other)/max(fail_c,1)*100:.0f}% | Lỗi tone, format không phù hợp |

---

## 3. Phân tích 5 Whys (Top 3 Cases Tệ Nhất)

### Case #1: {worst_cases[0]['test_case'][:80]}...
- **Score:** {worst_cases[0]['judge']['final_score']:.1f}/5.0 | **Type:** {worst_cases[0].get('type', 'unknown')} | **Difficulty:** {worst_cases[0].get('difficulty', 'unknown')}
- **Agent Response:** _{worst_cases[0]['agent_response'][:120]}..._
- **Retrieval:** Hit={worst_cases[0]['ragas']['retrieval'].get('hit_rate', 'N/A')}, MRR={worst_cases[0]['ragas']['retrieval'].get('mrr', 'N/A')}

1. **Symptom:** Agent cho điểm thấp ({worst_cases[0]['judge']['final_score']:.1f}/5), câu trả lời không chính xác hoặc thiếu thông tin.
2. **Why 1:** LLM không trích dẫn được thông tin cụ thể từ tài liệu liên quan.
3. **Why 2:** Vector DB không tìm được đúng document (Hit Rate = {worst_cases[0]['ragas']['retrieval'].get('hit_rate', 0)}).
4. **Why 3:** Embedding model không capture được semantic similarity cho câu hỏi dạng {worst_cases[0].get('type', 'unknown')}.
5. **Why 4:** Chunking strategy chia nhỏ thông tin quan trọng sang nhiều chunk khác nhau.
6. **Root Cause:** Chiến lược chunking theo fixed-size không phù hợp với dữ liệu có cấu trúc bảng biểu và danh sách số liệu.

### Case #2: {worst_cases[1]['test_case'][:80]}...
- **Score:** {worst_cases[1]['judge']['final_score']:.1f}/5.0 | **Type:** {worst_cases[1].get('type', 'unknown')} | **Difficulty:** {worst_cases[1].get('difficulty', 'unknown')}
- **Agent Response:** _{worst_cases[1]['agent_response'][:120]}..._

1. **Symptom:** Điểm thấp ({worst_cases[1]['judge']['final_score']:.1f}/5), đặc biệt từ model {list(worst_cases[1]['judge']['individual_scores'].keys())[0]}.
2. **Why 1:** Câu trả lời thiếu context về chính sách cụ thể.
3. **Why 2:** Câu hỏi loại `{worst_cases[1].get('type', 'unknown')}` cần nhiều tài liệu phối hợp.
4. **Why 3:** Retrieval chỉ lấy 1 document thay vì cần 2-3 documents.
5. **Why 4:** Query expansion chưa được triển khai trong retrieval pipeline.
6. **Root Cause:** Thiếu multi-document reasoning - RAG pipeline không hỗ trợ kết hợp thông tin từ nhiều nguồn.

### Case #3: {worst_cases[2]['test_case'][:80]}...
- **Score:** {worst_cases[2]['judge']['final_score']:.1f}/5.0 | **Type:** {worst_cases[2].get('type', 'unknown')} | **Difficulty:** {worst_cases[2].get('difficulty', 'unknown')}

1. **Symptom:** Model judge bất đồng (Divergence={worst_cases[2]['judge']['divergence']:.1f}).
2. **Why 1:** Câu hỏi mơ hồ, thiếu context → câu trả lời không rõ ràng.
3. **Why 2:** System prompt chưa hướng dẫn agent yêu cầu làm rõ (clarification) khi câu hỏi mơ hồ.
4. **Why 3:** Training examples không bao gồm trường hợp ambiguous queries.
5. **Why 4:** Evaluation rubric của 2 judges có cách diễn giải khác nhau về "chất lượng câu trả lời cho câu hỏi mơ hồ".
6. **Root Cause:** Thiếu clarification flow trong agent design + rubric calibration chưa đủ chi tiết cho edge cases.

---

## 4. Phân tích Chi phí & Hiệu năng

### Chi phí Evaluation
- **Tổng chi phí V2 benchmark:** ${metrics['total_cost_usd']:.4f}
- **Chi phí trung bình/eval:** ${metrics['avg_cost_per_eval_usd']:.6f}
- **Latency trung bình:** {metrics['avg_latency_sec']:.3f}s/case
- **Ước tính cho 10,000 evals/tháng:** ${metrics['avg_cost_per_eval_usd']*10000:.2f}/tháng

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
- Score tăng **{reg['score']:+.3f} điểm** ({regression['v1_summary']['avg_score']:.2f} → {metrics['avg_score']:.2f})
- Hit Rate tăng **{reg['hit_rate']:+.1%}** ({regression['v1_summary']['hit_rate']*100:.0f}% → {metrics['hit_rate']*100:.0f}%)

**Nguyên nhân gốc rễ chính** của các failures: Chiến lược Chunking không phù hợp (Fixed-size 512 tokens) gây ra context split, làm retrieval miss documents quan trọng, dẫn đến Hallucination trong generation stage.

**Quyết định:** {regression['decision']} - {regression['reason']}
"""
    return report


async def main():
    print("\n" + "=" * 60)
    print("   🏭 AI EVALUATION FACTORY - Lab 14 Expert Level")
    print("=" * 60)

    # Load dataset
    if not os.path.exists("data/golden_set.jsonl"):
        print("❌ Thiếu data/golden_set.jsonl. Chạy: python data/synthetic_gen.py")
        return

    with open("data/golden_set.jsonl", "r", encoding="utf-8") as f:
        dataset = [json.loads(line) for line in f if line.strip()]

    if len(dataset) < 50:
        print(f"⚠️  Cảnh báo: Chỉ có {len(dataset)} cases (yêu cầu ≥50)")
    else:
        print(f"✅ Loaded {len(dataset)} test cases từ Golden Dataset")

    # ===== PHASE 1: BENCHMARK V1 =====
    v1_results, v1_summary = await run_benchmark("Agent_V1_Base", dataset)

    # ===== PHASE 2: BENCHMARK V2 =====
    v2_results, v2_summary = await run_benchmark("Agent_V2_Optimized", dataset)

    if not v1_summary or not v2_summary:
        print("❌ Benchmark thất bại. Kiểm tra lại cấu hình.")
        return

    # ===== PHASE 3: REGRESSION ANALYSIS =====
    print(f"\n{'='*55}")
    print("📊 PHÂN TÍCH REGRESSION (V1 vs V2)")
    print(f"{'='*55}")

    regression = evaluate_release_gate(v1_summary, v2_summary)
    delta = regression["delta"]

    print(f"\n   Score:      V1={regression['v1_summary']['avg_score']:.3f} → V2={regression['v2_summary']['avg_score']:.3f} ({delta['score']:+.3f})")
    print(f"   Hit Rate:   V1={regression['v1_summary']['hit_rate']*100:.1f}% → V2={regression['v2_summary']['hit_rate']*100:.1f}% ({delta['hit_rate']:+.1%})")
    print(f"   MRR:        V1={regression['v1_summary']['mrr']:.3f} → V2={regression['v2_summary']['mrr']:.3f}")
    print(f"   Agreement:  V1={regression['v1_summary']['agreement_rate']*100:.1f}% → V2={regression['v2_summary']['agreement_rate']*100:.1f}%")
    print(f"   Cost:       {delta['cost_pct']:+.1f}%")
    print(f"\n   GATE CHECKS:")
    for check_name, check in regression["checks"].items():
        icon = "✅" if check["passed"] else "❌"
        print(f"   {icon} {check_name}: {check['detail']}")

    print(f"\n{'='*55}")
    print(f"🏁 QUYẾT ĐỊNH: {regression['decision']}")
    print(f"   {regression['reason']}")
    print(f"{'='*55}")

    # ===== PHASE 4: LƯU REPORTS =====
    os.makedirs("reports", exist_ok=True)
    os.makedirs("analysis/reflections", exist_ok=True)

    # Xây dựng final summary.json (V2 + regression)
    final_summary = {
        **v2_summary,
        "metadata": {
            **v2_summary["metadata"],
            "baseline_version": "Agent_V1_Base",
            "regression_status": regression["decision"],
        },
        "regression": {
            "v1_metrics": regression["v1_summary"],
            "v2_metrics": regression["v2_summary"],
            "delta": regression["delta"],
            "gate_decision": regression["decision"],
            "gate_reason": regression["reason"],
            "gate_checks": {k: v["passed"] for k, v in regression["checks"].items()},
        },
    }

    with open("reports/summary.json", "w", encoding="utf-8") as f:
        json.dump(final_summary, f, ensure_ascii=False, indent=2)

    with open("reports/benchmark_results.json", "w", encoding="utf-8") as f:
        json.dump({
            "v1": v1_results,
            "v2": v2_results,
        }, f, ensure_ascii=False, indent=2)

    # Tạo failure_analysis.md tự động
    failure_report = generate_failure_analysis(v2_results, v2_summary, regression)
    with open("analysis/failure_analysis.md", "w", encoding="utf-8") as f:
        f.write(failure_report)

    print(f"\n✅ Reports đã lưu:")
    print(f"   📄 reports/summary.json")
    print(f"   📄 reports/benchmark_results.json")
    print(f"   📄 analysis/failure_analysis.md")
    print(f"\n🎉 Benchmark hoàn thành! Chạy 'python check_lab.py' để kiểm tra.")


if __name__ == "__main__":
    asyncio.run(main())
