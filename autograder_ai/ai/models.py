import numpy as np

class MockModel:
    """
    A dummy model class for testing the AI inference pipeline.
    Implements predict_proba as expected by AIInferenceEngine.
    """
    def predict_proba(self, X):
        return np.array([[0.2, 0.8]])
