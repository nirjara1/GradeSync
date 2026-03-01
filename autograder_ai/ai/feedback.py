from typing import List, Dict, Any
from ..schemas import FeedbackItem

class FeedbackGenerator:
    def generate_feedback(self, stdout: str, stderr: str, test_results: List[Any]) -> List[FeedbackItem]:
        feedback = []
        
        # 1. Compilation/Runtime Errors
        if stderr and len(stderr) > 0:
            feedback.append(FeedbackItem(
                category='Runtime Error',
                message=f"Error log detected: {stderr[:500]}...", # Truncate
                severity='critical'
            ))
            
        # 2. Test Failures
        failed_tests = [t for t in test_results if not t.passed]
        if failed_tests:
            for t in failed_tests:
                feedback.append(FeedbackItem(
                    category='Logic Error',
                    message=f"Test '{t.name}' failed. Output: {t.output[:200]}...",
                    severity='warning'
                ))
        
        # 3. Success
        if not failed_tests and not stderr:
             feedback.append(FeedbackItem(
                category='Success',
                message="All tests passed!",
                severity='info'
            ))
            
        return feedback
