import os
import json
import logging
from typing import Optional
from .schemas import GradeRequest, GradeResponse, TestResult
from .runners.python_runner import PythonRunner
from .runners.java_runner import JavaRunner
from .scoring.rubric import Rubric
from .ai.feedback import FeedbackGenerator
from .ai.similarity import SimilarityEngine
from .ai.inference_ai_likelihood import AIInferenceEngine

logger = logging.getLogger(__name__)

class GradingService:
    def __init__(self):
        self.similarity_engine = SimilarityEngine()
        # Path relative to module root or configured
        self.ai_engine = AIInferenceEngine("autograder_ai/ai/models/ai_likelihood.joblib")
        
    def grade_submission(self, request: GradeRequest) -> GradeResponse:
        try:
            # 1. Select Runner
            if request.language == 'python':
                runner = PythonRunner()
            elif request.language == 'java':
                runner = JavaRunner()
            else:
                return GradeResponse(
                    success=False, total_score=0, max_score=0, breakdown=[], 
                    feedback=[], error=f"Unsupported language: {request.language}"
                )
            
            # 2. Execution
            # In a real app, assignment_config would be loaded from disk/DB
            # For prototype, we assume it's passed or loaded from a file
            config = {}
            if os.path.exists(request.assignment_config_path):
                with open(request.assignment_config_path, 'r') as f:
                    config = json.load(f)
            
            stdout, stderr, exit_code = runner.run_submission(request.submission_path, config)
            
            # 3. Parse Results (Simplistic)
            # Python runner produces report.json (mocked) or we parse stdout
            # For this prototype, we'll try to parse a JSON from stdout if runner printed one,
            # or parse standard test output. 
            
            # MOCKING for prototype if no actual tests ran:
            test_results = []
            if "report.json" in stdout: # Validation that pytest ran
                pass # parse report
                
            # fallback/mock parsing logic for demo purposes
            # If exit_code is 0, assume pass.
            test_results.append(TestResult(
                name="Compilation/Execution",
                passed=(exit_code == 0),
                score=10 if exit_code == 0 else 0,
                max_score=10,
                output=stdout + stderr
            ))
            
            # 4. Scoring
            rubric = Rubric(config.get('rubric', {'Compilation/Execution': 10}))
            total_score = rubric.calculate_score(test_results)
            max_score = sum(config.get('rubric', {'Compilation/Execution': 10}).values())
            
            # 5. Feedback
            feedback_gen = FeedbackGenerator()
            feedback = feedback_gen.generate_feedback(stdout, stderr, test_results)
            
            # 6. AI & Similarity
            # Extract code text for analysis
            submission_text = ""
            for root, _, files in os.walk(request.submission_path):
                for file in files:
                    if file.endswith('.py') or file.endswith('.java'):
                        try:
                            with open(os.path.join(root, file), 'r', errors='ignore') as f:
                                submission_text += f.read() + "\n"
                        except: pass
            
            ai_likelihood = self.ai_engine.predict(submission_text)
            
            # Corpus dir would be submissions/assignment_id/
            corpus_dir = os.path.join("autograder_ai/submissions", request.assignment_id)
            plagiarism = self.similarity_engine.check_similarity(submission_text, corpus_dir)
            
            # 7. Construct Response
            response = GradeResponse(
                success=True,
                total_score=total_score,
                max_score=max_score,
                breakdown=test_results,
                feedback=feedback,
                ai_likelihood=ai_likelihood,
                ai_explanation="Detailed explanation placeholder",
                plagiarism_matches=[{'file': f, 'score': s} for f, s in plagiarism]
            )
            
            # 8. Save Artifact
            report_dir = os.path.join("autograder_ai/artifacts", request.assignment_id, request.student_id)
            os.makedirs(report_dir, exist_ok=True)
            with open(os.path.join(report_dir, "report.json"), "w") as f:
                f.write(response.model_dump_json(indent=2))
                
            return response
            
        except Exception as e:
            logger.exception("Grading failed")
            return GradeResponse(
                success=False, total_score=0, max_score=0, breakdown=[], 
                feedback=[], error=str(e)
            )
