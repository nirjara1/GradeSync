from typing import List, Dict, Any
from ..schemas import TestResult

class Rubric:
    def __init__(self, rubric_config: Dict[str, float]):
        """
        rubric_config: { 'test_name_or_regex': weight }
        """
        self.config = rubric_config
    
    def calculate_score(self, test_results: List[TestResult]) -> float:
        total_score = 0
        total_weight = sum(self.config.values())
        
        if total_weight == 0:
            return 0
            
        for result in test_results:
            # Simple exact match for prototype
            # Production would use regex matching
            weight = self.config.get(result.name, 0)
            if result.passed:
                total_score += weight
                
        return total_score
