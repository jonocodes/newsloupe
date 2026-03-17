import numpy as np
from typing import Optional
from datetime import datetime


class MLScorer:
    """
    Machine learning scorer that predicts click probability based on historical clicks.

    Uses a simple logistic regression model trained on click history.
    Falls back to None predictions if insufficient training data (<20 clicks).
    """

    def __init__(self, min_training_samples: int = 20):
        self.min_training_samples = min_training_samples
        self.model = None
        self.feature_mean = None
        self.feature_std = None

    def _extract_features(self, scored_stories: list) -> np.ndarray:
        """
        Extract feature vectors from scored stories.

        Features:
        - tfidf_score
        - embedding_score
        - delta (embed - tfidf)
        - hn_points (normalized)
        - hn_comments (normalized)
        - hour_of_day (0-23, cyclical encoding)
        """
        features = []
        for story in scored_stories:
            # Get time features if available
            hour = 12  # Default midday
            if hasattr(story, 'created_at') and story.created_at:
                try:
                    dt = datetime.fromisoformat(story.created_at.replace('Z', '+00:00'))
                    hour = dt.hour
                except (ValueError, AttributeError):
                    pass

            # Cyclical encoding of hour (sin/cos to preserve 23->0 continuity)
            hour_sin = np.sin(2 * np.pi * hour / 24)
            hour_cos = np.cos(2 * np.pi * hour / 24)

            feature_vec = [
                story.tfidf_score if hasattr(story, 'tfidf_score') else 0.0,
                story.embedding_score if hasattr(story, 'embedding_score') else 0.0,
                story.delta if hasattr(story, 'delta') else 0.0,
                float(story.hn_points if hasattr(story, 'hn_points') else 0) / 100.0,  # Normalize
                float(story.hn_comments if hasattr(story, 'hn_comments') else 0) / 50.0,  # Normalize
                hour_sin,
                hour_cos,
            ]
            features.append(feature_vec)

        return np.array(features)

    def _extract_features_from_clicks(self, clicks: list[dict]) -> np.ndarray:
        """Extract features from click history records."""
        features = []
        for click in clicks:
            # Get time features
            hour = 12  # Default
            if 'clicked_at' in click:
                try:
                    dt = datetime.fromisoformat(click['clicked_at'].replace('Z', '+00:00'))
                    hour = dt.hour
                except (ValueError, AttributeError):
                    pass

            hour_sin = np.sin(2 * np.pi * hour / 24)
            hour_cos = np.cos(2 * np.pi * hour / 24)

            feature_vec = [
                click.get('tfidf_score', 0.0) or 0.0,
                click.get('embedding_score', 0.0) or 0.0,
                click.get('delta', 0.0) or 0.0,
                float(click.get('hn_points', 0) or 0) / 100.0,
                float(click.get('hn_comments', 0) or 0) / 50.0,
                hour_sin,
                hour_cos,
            ]
            features.append(feature_vec)

        return np.array(features)

    def train(self, clicks: list[dict]) -> bool:
        """
        Train the model on click history.

        Returns True if training succeeded, False if insufficient data.
        """
        if len(clicks) < self.min_training_samples:
            return False

        try:
            from sklearn.linear_model import LogisticRegression
        except ImportError:
            raise ImportError(
                "scikit-learn is required for ML scoring. "
                "Install with: pip install scikit-learn"
            )

        # Extract features from clicks (all positive examples)
        X_positive = self._extract_features_from_clicks(clicks)
        y_positive = np.ones(len(X_positive))

        # For negative examples, we synthesize by permuting features
        # This creates "unlikely" combinations that the user didn't click
        # Simple approach: create random low-scoring synthetic examples
        n_synthetic = min(len(clicks) * 2, 200)  # Generate 2x negatives, cap at 200
        np.random.seed(42)

        X_negative = []
        for _ in range(n_synthetic):
            # Create synthetic negative by mixing low scores with random time
            hour = np.random.randint(0, 24)
            hour_sin = np.sin(2 * np.pi * hour / 24)
            hour_cos = np.cos(2 * np.pi * hour / 24)

            synthetic = [
                np.random.uniform(0, 0.3),  # Low tfidf
                np.random.uniform(0, 0.3),  # Low embedding
                np.random.uniform(-0.2, 0.2),  # Small delta
                np.random.uniform(0, 0.5),  # Low points
                np.random.uniform(0, 0.3),  # Low comments
                hour_sin,
                hour_cos,
            ]
            X_negative.append(synthetic)

        X_negative = np.array(X_negative)
        y_negative = np.zeros(len(X_negative))

        # Combine positive and negative examples
        X = np.vstack([X_positive, X_negative])
        y = np.concatenate([y_positive, y_negative])

        # Normalize features (important for logistic regression)
        self.feature_mean = X.mean(axis=0)
        self.feature_std = X.std(axis=0) + 1e-8  # Avoid division by zero
        X_normalized = (X - self.feature_mean) / self.feature_std

        # Train logistic regression
        self.model = LogisticRegression(
            max_iter=1000,
            random_state=42,
            class_weight='balanced',  # Handle class imbalance
        )
        self.model.fit(X_normalized, y)

        return True

    def predict(self, scored_stories: list) -> Optional[list[float]]:
        """
        Predict click probabilities for a list of scored stories.

        Returns None if model hasn't been trained.
        Returns list of probabilities [0.0-1.0] otherwise.
        """
        if self.model is None:
            return None

        X = self._extract_features(scored_stories)
        X_normalized = (X - self.feature_mean) / self.feature_std

        # Predict probabilities for the positive class (click)
        probabilities = self.model.predict_proba(X_normalized)[:, 1]

        return probabilities.tolist()

    def get_feature_importance(self) -> Optional[dict]:
        """
        Get feature importance scores (coefficients from logistic regression).

        Returns None if model hasn't been trained.
        """
        if self.model is None:
            return None

        feature_names = [
            'tfidf_score',
            'embedding_score',
            'delta',
            'hn_points',
            'hn_comments',
            'hour_sin',
            'hour_cos',
        ]

        coefficients = self.model.coef_[0]
        return dict(zip(feature_names, coefficients.tolist()))
