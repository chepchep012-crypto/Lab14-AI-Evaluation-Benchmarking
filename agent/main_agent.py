"""
Main Agent - Mô phỏng RAG Agent với 2 phiên bản V1 và V2.
V2 có retrieval accuracy cao hơn V1 nhờ cải tiến chunking và re-ranking.
"""
import asyncio
import hashlib
import random
from typing import Dict, List

# Toàn bộ document IDs trong knowledge base
ALL_DOC_IDS = [f"doc_{i:03d}" for i in range(1, 21)]

# Cấu hình chất lượng theo phiên bản
VERSION_CONFIG = {
    "v1": {
        "retrieval_accuracy": 0.70,   # 70% hit rate
        "answer_quality": 0.72,       # Chất lượng câu trả lời
        "tokens_per_query": (120, 200),  # Range token usage
        "latency_range": (0.4, 1.2),
    },
    "v2": {
        "retrieval_accuracy": 0.87,   # 87% hit rate (cải thiện nhờ re-ranking)
        "answer_quality": 0.88,
        "tokens_per_query": (150, 220),
        "latency_range": (0.3, 0.9),
    }
}

SAMPLE_ANSWERS = {
    "easy": [
        "Dựa trên tài liệu hệ thống, {question} được xử lý theo quy trình chuẩn. Bạn cần thực hiện các bước sau trong Settings của tài khoản.",
        "Theo chính sách hiện hành, {question} được giải quyết như sau. Vui lòng tham khảo hướng dẫn chi tiết trong Help Center.",
    ],
    "medium": [
        "Đây là vấn đề kỹ thuật thường gặp. Để giải quyết {question}, bạn cần kiểm tra cấu hình và thực hiện các bước khắc phục.",
        "Câu hỏi này liên quan đến nhiều tính năng. Tôi sẽ giải thích từng bước để bạn có thể xử lý {question} hiệu quả.",
    ],
    "hard": [
        "Đây là câu hỏi phức tạp đòi hỏi phân tích nhiều yếu tố. Tôi sẽ cung cấp hướng dẫn chi tiết về {question}.",
        "Vấn đề này có nhiều khía cạnh cần xem xét. Để giải quyết triệt để {question}, hãy thực hiện theo quy trình sau.",
    ],
    "adversarial": [
        "Tôi không thể hỗ trợ yêu cầu này vì nằm ngoài phạm vi hỗ trợ khách hàng hoặc vi phạm chính sách bảo mật.",
        "Yêu cầu này không phù hợp với chính sách sử dụng dịch vụ. Nếu bạn có câu hỏi hợp lệ, tôi sẵn sàng hỗ trợ.",
    ],
    "edge_case": [
        "Đây là tình huống đặc biệt. Tôi sẽ hướng dẫn bạn xử lý {question} theo từng trường hợp cụ thể.",
        "Trường hợp này có thể có nhiều nguyên nhân. Hãy thử các giải pháp sau để khắc phục {question}.",
    ],
}


def _get_rng(seed_str: str, extra: int = 0) -> random.Random:
    """Tạo random number generator xác định từ string."""
    seed = int(hashlib.md5(seed_str.encode()).hexdigest()[:8], 16) + extra
    return random.Random(seed)


class MainAgent:
    """
    RAG Agent mô phỏng với khả năng điều chỉnh chất lượng theo phiên bản.
    V1: Baseline agent với retrieval accuracy ~70%
    V2: Optimized agent với re-ranking, accuracy ~87%
    """

    def __init__(self, version: str = "v1"):
        if version not in VERSION_CONFIG:
            raise ValueError(f"Version phải là 'v1' hoặc 'v2', nhận được: {version}")
        self.version = version
        self.config = VERSION_CONFIG[version]
        self.name = f"SupportAgent-{version.upper()}"

    async def query(self, question: str, hint_ids: List[str] = None) -> Dict:
        """
        Mô phỏng quy trình RAG: Retrieve → Augment → Generate.
        hint_ids: ground truth IDs dùng cho simulation (production không cần).
        """
        rng = _get_rng(question + self.version)

        # Giả lập latency thực tế
        lo, hi = self.config["latency_range"]
        await asyncio.sleep(rng.uniform(lo * 0.1, hi * 0.1))

        retrieved_ids = self._simulate_retrieval(question, hint_ids or [], rng)
        answer = self._simulate_generation(question, retrieved_ids, rng)
        tokens = rng.randint(*self.config["tokens_per_query"])

        return {
            "answer": answer,
            "retrieved_ids": retrieved_ids,
            "contexts": [f"[{doc_id}] Đoạn trích từ tài liệu {doc_id}..." for doc_id in retrieved_ids],
            "metadata": {
                "model": "gpt-4o-mini" if self.version == "v1" else "gpt-4o",
                "tokens_used": tokens,
                "version": self.version,
                "sources": [f"{rid}.pdf" for rid in retrieved_ids[:2]],
            },
        }

    def _simulate_retrieval(self, question: str, expected_ids: List[str], rng: random.Random) -> List[str]:
        """
        Mô phỏng vector retrieval với accuracy phụ thuộc vào version.
        V2 dùng re-ranking nên hit rate cao hơn V1.
        """
        accuracy = self.config["retrieval_accuracy"]
        retrieved = []

        # Với mỗi expected doc, có probability = accuracy để retrieve đúng
        for doc_id in expected_ids:
            if rng.random() < accuracy:
                retrieved.append(doc_id)

        # Thêm "noise" documents (documents không liên quan) để thực tế hơn
        noise_count = rng.randint(1, 3)
        noise_pool = [d for d in ALL_DOC_IDS if d not in expected_ids and d not in retrieved]
        if noise_pool:
            # V2 ít noise hơn V1 nhờ re-ranking
            max_noise = 1 if self.version == "v2" else 2
            noise_count = min(noise_count, max_noise)
            noises = rng.sample(noise_pool, min(noise_count, len(noise_pool)))
            retrieved.extend(noises)

        # Đảm bảo luôn có ít nhất 1 document, tối đa 5
        if not retrieved:
            retrieved = rng.sample(ALL_DOC_IDS, 1)

        rng.shuffle(retrieved)
        return retrieved[:5]

    def _simulate_generation(self, question: str, retrieved_ids: List[str], rng: random.Random) -> str:
        """
        Mô phỏng LLM generation dựa trên retrieved context.
        V2 có câu trả lời chi tiết hơn V1.
        """
        # Xác định loại câu hỏi để chọn mẫu phù hợp
        q_lower = question.lower()
        if any(kw in q_lower for kw in ["ignore", "pretend", "jailbreak", "system prompt", "giả sử", "thủ đô"]):
            difficulty = "adversarial"
        elif len(question) > 150:
            difficulty = "hard"
        elif any(kw in q_lower for kw in ["làm thế nào", "quy trình", "cách"]):
            difficulty = "medium"
        else:
            difficulty = "easy"

        templates = SAMPLE_ANSWERS.get(difficulty, SAMPLE_ANSWERS["easy"])
        template = rng.choice(templates)

        # V2 thêm thông tin từ retrieved docs (câu trả lời tốt hơn)
        answer = template.format(question=question[:50] + "...")
        if self.version == "v2" and retrieved_ids:
            answer += f" (Nguồn tham khảo: {', '.join(retrieved_ids[:2])})"

        return answer
