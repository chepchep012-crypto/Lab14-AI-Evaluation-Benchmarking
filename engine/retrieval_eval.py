"""
Retrieval Evaluator - Tính toán Hit Rate và MRR cho Vector DB.
Đánh giá chất lượng retrieval stage trước khi đánh giá generation.
"""
from typing import List, Dict, Optional


class RetrievalEvaluator:
    """
    Đánh giá chất lượng retrieval với các metrics chuẩn ngành:
    - Hit Rate (HR@K): Tỉ lệ câu hỏi được retrieve đúng ít nhất 1 document liên quan
    - MRR (Mean Reciprocal Rank): Vị trí trung bình của document liên quan đầu tiên
    """

    def __init__(self, top_k: int = 5):
        self.top_k = top_k

    def calculate_hit_rate(
        self, expected_ids: List[str], retrieved_ids: List[str], top_k: Optional[int] = None
    ) -> float:
        """
        Hit Rate @ K: Kiểm tra xem ít nhất 1 expected_id có trong top_k retrieved không.

        Args:
            expected_ids: Danh sách doc IDs cần tìm (ground truth)
            retrieved_ids: Danh sách doc IDs đã được retrieve (theo thứ tự relevance)
            top_k: Số lượng kết quả hàng đầu xem xét

        Returns:
            1.0 nếu hit, 0.0 nếu miss. None nếu không có expected_ids.
        """
        if not expected_ids:
            return None  # N/A cho adversarial cases không cần retrieve

        k = top_k or self.top_k
        top_retrieved = retrieved_ids[:k]
        hit = any(doc_id in top_retrieved for doc_id in expected_ids)
        return 1.0 if hit else 0.0

    def calculate_mrr(self, expected_ids: List[str], retrieved_ids: List[str]) -> float:
        """
        Mean Reciprocal Rank: Đo lường vị trí của document liên quan đầu tiên.
        MRR = 1/rank của kết quả liên quan đầu tiên. Nếu không tìm thấy = 0.

        Args:
            expected_ids: Ground truth document IDs
            retrieved_ids: Retrieved document IDs (theo thứ tự, index 0 = rank 1)

        Returns:
            Float từ 0.0 đến 1.0. Cao hơn = tốt hơn.
        """
        if not expected_ids:
            return None  # N/A

        for rank, doc_id in enumerate(retrieved_ids, start=1):
            if doc_id in expected_ids:
                return 1.0 / rank
        return 0.0

    def calculate_precision_at_k(
        self, expected_ids: List[str], retrieved_ids: List[str], top_k: Optional[int] = None
    ) -> float:
        """
        Precision@K: Tỉ lệ documents liên quan trong top K kết quả.
        """
        if not expected_ids:
            return None

        k = top_k or self.top_k
        top_retrieved = retrieved_ids[:k]
        relevant_count = sum(1 for doc_id in top_retrieved if doc_id in expected_ids)
        return relevant_count / k if k > 0 else 0.0

    def evaluate_single(self, expected_ids: List[str], retrieved_ids: List[str]) -> Dict:
        """Tính toán tất cả retrieval metrics cho một test case."""
        hit_rate = self.calculate_hit_rate(expected_ids, retrieved_ids)
        mrr = self.calculate_mrr(expected_ids, retrieved_ids)
        precision = self.calculate_precision_at_k(expected_ids, retrieved_ids)

        return {
            "hit_rate": hit_rate,
            "mrr": mrr,
            "precision_at_k": precision,
            "expected_count": len(expected_ids),
            "retrieved_count": len(retrieved_ids),
            "is_retrieval_case": len(expected_ids) > 0,
        }

    async def evaluate_batch(self, results: List[Dict]) -> Dict:
        """
        Tính toán aggregate retrieval metrics từ danh sách kết quả benchmark.
        Chỉ tính trung bình trên các cases có expected_retrieval_ids (bỏ qua adversarial).

        Args:
            results: List kết quả từ runner, mỗi item có trường 'ragas.retrieval'

        Returns:
            Dict chứa avg_hit_rate, avg_mrr, coverage, breakdown by difficulty
        """
        retrieval_cases = [r for r in results if r.get("ragas", {}).get("retrieval", {}).get("is_retrieval_case")]
        non_retrieval_cases = [r for r in results if not r.get("ragas", {}).get("retrieval", {}).get("is_retrieval_case")]

        if not retrieval_cases:
            return {"avg_hit_rate": 0.0, "avg_mrr": 0.0, "total_retrieval_cases": 0}

        hit_rates = [r["ragas"]["retrieval"]["hit_rate"] for r in retrieval_cases if r["ragas"]["retrieval"]["hit_rate"] is not None]
        mrrs = [r["ragas"]["retrieval"]["mrr"] for r in retrieval_cases if r["ragas"]["retrieval"]["mrr"] is not None]
        precisions = [r["ragas"]["retrieval"]["precision_at_k"] for r in retrieval_cases if r["ragas"]["retrieval"]["precision_at_k"] is not None]

        # Breakdown theo độ khó
        difficulty_stats = {}
        for r in retrieval_cases:
            diff = r.get("difficulty", "unknown")
            if diff not in difficulty_stats:
                difficulty_stats[diff] = {"count": 0, "hit_sum": 0.0, "mrr_sum": 0.0}
            hr = r["ragas"]["retrieval"].get("hit_rate", 0) or 0
            mrr = r["ragas"]["retrieval"].get("mrr", 0) or 0
            difficulty_stats[diff]["count"] += 1
            difficulty_stats[diff]["hit_sum"] += hr
            difficulty_stats[diff]["mrr_sum"] += mrr

        for diff in difficulty_stats:
            cnt = difficulty_stats[diff]["count"]
            difficulty_stats[diff]["avg_hit_rate"] = round(difficulty_stats[diff]["hit_sum"] / cnt, 4)
            difficulty_stats[diff]["avg_mrr"] = round(difficulty_stats[diff]["mrr_sum"] / cnt, 4)

        return {
            "avg_hit_rate": round(sum(hit_rates) / len(hit_rates), 4) if hit_rates else 0.0,
            "avg_mrr": round(sum(mrrs) / len(mrrs), 4) if mrrs else 0.0,
            "avg_precision_at_k": round(sum(precisions) / len(precisions), 4) if precisions else 0.0,
            "total_retrieval_cases": len(retrieval_cases),
            "non_retrieval_cases": len(non_retrieval_cases),
            "hit_cases": sum(1 for hr in hit_rates if hr == 1.0),
            "miss_cases": sum(1 for hr in hit_rates if hr == 0.0),
            "breakdown_by_difficulty": difficulty_stats,
        }
