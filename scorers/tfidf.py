from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


class TfidfScorer:
    def score(self, interest_titles: list[str], story_titles: list[str]) -> list[float]:
        if not interest_titles or not story_titles:
            return [0.0] * len(story_titles)

        corpus = interest_titles + story_titles
        vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2))
        tfidf_matrix = vectorizer.fit_transform(corpus)

        n_interests = len(interest_titles)
        interest_vectors = tfidf_matrix[:n_interests]
        story_vectors = tfidf_matrix[n_interests:]

        similarities = cosine_similarity(story_vectors, interest_vectors)
        return [float(row.max()) for row in similarities]
