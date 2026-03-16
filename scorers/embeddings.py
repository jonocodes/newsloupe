import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
from sentence_transformers import SentenceTransformer


class EmbeddingScorer:
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self.model_name = model_name
        self.model = SentenceTransformer(model_name)

    def encode(self, texts: list[str]) -> np.ndarray:
        return self.model.encode(texts, show_progress_bar=False)

    def score(self, interest_embeddings: np.ndarray, story_titles: list[str]) -> list[float]:
        if len(story_titles) == 0 or len(interest_embeddings) == 0:
            return [0.0] * len(story_titles)

        story_embeddings = self.encode(story_titles)
        similarities = cosine_similarity(story_embeddings, interest_embeddings)
        return [float(row.max()) for row in similarities]
