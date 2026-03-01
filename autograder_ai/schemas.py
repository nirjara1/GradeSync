from pydantic import BaseModel
from typing import List, Dict, Optional, Any

class GradeRequest(BaseModel):
    assignment_id: str
    student_id: str
    language: str  # 'python' or 'java'
    submission_path: str
    assignment_config_path: str
    
class TestResult(BaseModel):
    name: str
    passed: bool
    score: float
    max_score: float
    output: str
    error: Optional[str] = None

class FeedbackItem(BaseModel):
    category: str  # 'Compile Error', 'Logic Error', 'Style', 'AI Detection'
    message: str
    severity: str  # 'info', 'warning', 'critical'

class GradeResponse(BaseModel):
    success: bool
    total_score: float
    max_score: float
    breakdown: List[TestResult]
    feedback: List[FeedbackItem]
    ai_likelihood: Optional[float] = None
    ai_explanation: Optional[str] = None
    plagiarism_matches: List[Dict[str, Any]] = []
    error: Optional[str] = None
