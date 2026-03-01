import joblib
import os
import numpy as np
from .features import extract_features

class AIInferenceEngine:
    def __init__(self, model_path: str):
        self.model_path = model_path
        self.model = None
        if os.path.exists(model_path):
            try:
                self.model = joblib.load(model_path)
            except Exception:
                pass
    
    def predict(self, code: str) -> float:
        """
        Returns probability of being AI generated (0.0 to 1.0)
        """
        if not self.model:
            return 0.0 # Default to human if no model
            
        features = extract_features(code)
        try:
             # Class 1 is AI
            prob = self.model.predict_proba(features)[0][1]
            return float(prob)
        except Exception:
            return 0.0
