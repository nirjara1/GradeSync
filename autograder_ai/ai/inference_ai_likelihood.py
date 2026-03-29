import joblib
import os
import logging
import numpy as np

# Ensure MockModel is in namespace for joblib.load if using dummy models
try:
    from .models import MockModel
except ImportError:
    MockModel = None

logger = logging.getLogger(__name__)

class AIInferenceEngine:
    def __init__(self, model_path: str):
        self.model_path = model_path
        self.model = None
        
        if os.path.exists(model_path):
            try:
                # Specific handling for potential serialization issues
                loaded_model = joblib.load(model_path)
                
                # Validation: check for predict_proba method
                if hasattr(loaded_model, 'predict_proba'):
                    self.model = loaded_model
                    logger.info(f"AI Model loaded successfully from {model_path}")
                else:
                    logger.error(f"Loaded object at {model_path} lacks 'predict_proba' method.")
            except (ModuleNotFoundError, AttributeError) as e:
                logger.error(f"Serialization error loading AI model at {model_path}: {e}")
            except Exception as e:
                logger.error(f"Unexpected error loading AI model at {model_path}: {e}")
        else:
            logger.warning(f"AI Model file NOT found at: {model_path}")
    
    def predict(self, code: str) -> float:
        """
        Returns probability of being AI generated (0.0 to 1.0)
        """
        if not self.model:
            return 0.0
            
        from .features import extract_features
        try:
            features = extract_features(code)
            # Class 1 is AI
            prob = self.model.predict_proba(features)[0][1]
            return float(prob)
        except Exception as e:
            logger.error(f"AI Prediction failed: {e}")
            return 0.0

    def predict_with_confidence(self, code: str):
        """
        Returns (likelihood_percentage, confidence_percentage, explanation)
        """
        if not self.model:
            return None, None, "AI analysis unavailable (Model missing)."
            
        prob = self.predict(code)
        likelihood_pct = round(prob * 100, 2) # Use 2 decimals for precision as suggested
        
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
            
        return likelihood_pct, round(confidence_base, 2), explanation
