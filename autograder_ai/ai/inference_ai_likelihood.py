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

    def predict_with_confidence(self, code: str):
        """
        Returns (likelihood_percentage, confidence_percentage, explanation)
        """
        if not self.model:
            return None, None, "AI analysis unavailable (Model missing)."
            
        prob = self.predict(code)
        likelihood_pct = round(prob * 100, 1)
        
        # Heuristic confidence based on score extremity
        confidence_base = 85.0
        if prob > 0.8 or prob < 0.2:
            confidence_base += 10.0
            
        if prob > 0.7:
            explanation = "Pattern analysis suggests likely AI-assisted generation."
        elif prob > 0.3:
            explanation = "Some patterns match AI tools, but inconclusive."
        else:
            explanation = "Code structure appears primarily human-written."
            
        return likelihood_pct, round(confidence_base, 1), explanation
