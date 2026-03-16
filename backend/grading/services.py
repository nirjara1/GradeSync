import os
import io
import zipfile
import logging
import ast
import re
from django.conf import settings
from .models import Submission, TestCase, TestResult, RuleSet, Assignment
from .sandbox import execute_code

logger = logging.getLogger(__name__)

# Import AI modules only when needed to avoid import errors
try:
    from autograder_ai.ai.inference_ai_likelihood import AIInferenceEngine
    from autograder_ai.ai.similarity import SimilarityEngine
    HAS_AI_MODULES = True
except ImportError:
    HAS_AI_MODULES = False
    logger.warning("autograder_ai modules not available")

def extract_code_from_file(file_field) -> tuple[str, int]:
    """Extracts text from a python/java file or a zip file. Returns (combined_text, num_extracted_files)"""
    if not file_field or not hasattr(file_field, 'name'):
        return "", 0
        
    try:
        file_name = file_field.name.lower()
        file_field.open('rb')
        file_content = file_field.read()
        file_field.close()
        
        if file_name.endswith('.zip'):
            combined_text = []
            files_count = 0
            with zipfile.ZipFile(io.BytesIO(file_content), 'r') as zf:
                for zip_info in zf.infolist():
                    if zip_info.is_dir() or zip_info.filename.startswith('__MACOSX'):
                        continue

                    original_name = zip_info.filename
                    lower_name = original_name.lower()

                    if lower_name.endswith('.py') or lower_name.endswith('.java'):
                        try:
                            content = zf.read(original_name).decode('utf-8', errors='ignore')
                            combined_text.append(content)
                            files_count += 1
                            logger.info(f"Extracted source file from zip: {original_name}")
                        except Exception as e:
                            logger.error(f"Failed reading zip member {original_name}: {e}")
            logger.info(f"Total files extracted from ZIP archive: {files_count}")
            return "\n\n".join(combined_text), files_count
        elif file_name.endswith('.py') or file_name.endswith('.java'):
            return file_content.decode('utf-8', errors='ignore'), 1
    except Exception as e:
        logger.error(f"Failed to extract code: {e}")
        
    return "", 0

def run_submission_analysis(submission_id) -> dict:
    """
    Runs AI detection and Plagiarism detection on a submission safely.
    Handles zip files, avoids self-matching, and saves results directly to the model.
    Returns a dictionary structured payload of the results.
    """
    try:
        submission = Submission.objects.select_related('assignment', 'student__user').get(id=submission_id)
        logger.info(f"Starting analysis for submission {submission_id}")
    except Submission.DoesNotExist:
        logger.error(f"Analysis failed: Submission {submission_id} does not exist")
        return {
            "status": "error",
            "submission_id": submission_id,
            "error": "Submission not found"
        }
        
    try:
        code_str, file_count = extract_code_from_file(submission.file_path)
        logger.info(f"Extracted {file_count} source files from submission {submission_id}")
        
        if not code_str.strip():
            # No valid code to analyze
            submission.ai_likelihood_score = None
            submission.ai_confidence_score = None
            submission.ai_explanation = "Analysis unavailable: No supported source files found."
            submission.plagiarism_score = None
            submission.plagiarism_confidence_score = None
            submission.plagiarism_match_info = "Analysis unavailable."
            submission.save(update_fields=[
                'ai_likelihood_score', 'ai_confidence_score', 'ai_explanation',
                'plagiarism_score', 'plagiarism_confidence_score', 'plagiarism_match_info'
            ])
            logger.warning(f"Analysis unavailable for submission {submission_id}: No valid scripts found inside ZIP or raw upload.")
            return {
                "status": "error",
                "submission_id": submission_id,
                "error": "No supported source files found."
            }

        # 1. AI Inference
        try:
            if HAS_AI_MODULES:
                model_path = os.path.join(settings.BASE_DIR.parent, 'autograder_ai', 'ai', 'models', 'rf_model.pkl')
                ai_engine = AIInferenceEngine(model_path)
                
                likelihood_pct, conf_pct, explanation = ai_engine.predict_with_confidence(code_str)
                
                submission.ai_likelihood_score = likelihood_pct
                submission.ai_confidence_score = conf_pct
                submission.ai_explanation = explanation
                logger.info(f"AI score for submission {submission_id}: {submission.ai_likelihood_score}")
            else:
                submission.ai_likelihood_score = None
                submission.ai_confidence_score = None
                submission.ai_explanation = "AI modules not available."
        except Exception as e:
            logger.error(f"AI Inference failed for submission {submission_id}: {e}")
            submission.ai_likelihood_score = None
            submission.ai_confidence_score = None
            submission.ai_explanation = "AI analysis unavailable."

        # 2. Plagiarism Detection
        try:
            if HAS_AI_MODULES:
                 # Build corpus from other submissions to the same assignment
                other_submissions = Submission.objects.filter(
                    assignment=submission.assignment
                ).exclude(id=submission.id)
                
                corpus_texts = {}
                for other_sub in other_submissions:
                    other_code, _ = extract_code_from_file(other_sub.file_path)
                    if other_code.strip():
                        identifier = f"Student: {other_sub.student.user.username}"
                        corpus_texts[identifier] = other_code
                        
                sim_engine = SimilarityEngine(n=3)
                sim_results = sim_engine.check_similarity_from_texts(code_str, corpus_texts)
                
                if sim_results:
                    top_match_file, sim_score = sim_results[0]
                    submission.plagiarism_score = round(sim_score * 100, 1)
                    
                    # Heuristic deterministic confidence since engine doesn't provide real confidence
                    confidence = round(80.0 + (sim_score * 15.0), 1)
                    submission.plagiarism_confidence_score = min(confidence, 100.0) 
                    
                    submission.plagiarism_match_info = f"Closest Match: {top_match_file}"
                else:
                    submission.plagiarism_score = 0.0
                    submission.plagiarism_confidence_score = 95.0
                    submission.plagiarism_match_info = "No significant similarities found."
            else:
                submission.plagiarism_score = None
                submission.plagiarism_confidence_score = None
                submission.plagiarism_match_info = "Plagiarism analysis unavailable."
            
            logger.info(f"Plagiarism score for submission {submission_id}: {submission.plagiarism_score}")
        except Exception as e:
            logger.error(f"Plagiarism detection failed for submission {submission_id}: {e}")
            submission.plagiarism_score = None
            submission.plagiarism_confidence_score = None
            submission.plagiarism_match_info = "Plagiarism analysis unavailable."
            
        submission.save(update_fields=[
            'ai_likelihood_score', 'ai_confidence_score', 'ai_explanation',
            'plagiarism_score', 'plagiarism_confidence_score', 'plagiarism_match_info'
        ])
        
        logger.info(f"Analysis completed for submission {submission_id}")
        return {
            "status": "ok",
            "submission_id": submission_id,
            "ai_likelihood_score": submission.ai_likelihood_score,
            "ai_confidence_score": submission.ai_confidence_score,
            "ai_explanation": submission.ai_explanation,
            "plagiarism_score": submission.plagiarism_score,
            "plagiarism_confidence_score": submission.plagiarism_confidence_score,
            "plagiarism_match_info": submission.plagiarism_match_info,
            "num_files_analyzed": file_count
        }
    except Exception as e:
        logger.error(f"Overall analysis failed for submission {submission_id}: {e}")
        return {
            "status": "error",
            "submission_id": submission_id,
            "error": str(e)
        }


def grade_submission(submission_id: int) -> dict:
    """
    Grade a submission by running all test cases and checking rules.
    
    Args:
        submission_id: ID of the submission to grade
        
    Returns:
        Dict with grading results including test results and rule violations
    """
    try:
        submission = Submission.objects.select_related('assignment').get(id=submission_id)
        logger.info(f"Starting grading for submission {submission_id}")
    except Submission.DoesNotExist:
        logger.error(f"Grading failed: Submission {submission_id} does not exist")
        return {
            "status": "error",
            "submission_id": submission_id,
            "error": "Submission not found"
        }
    
    try:
        # Extract student code
        code_str, _ = extract_code_from_file(submission.file_path)
        if not code_str.strip():
            submission.status = 'failed'
            submission.save(update_fields=['status'])
            return {
                "status": "error",
                "submission_id": submission_id,
                "error": "No valid source code found"
            }
        
        assignment = submission.assignment
        language = assignment.allowed_language.lower()
        
        # Mark as grading
        submission.status = 'grading'
        submission.save(update_fields=['status'])
        
        # Get all test cases for this assignment
        test_cases = TestCase.objects.filter(assignment=assignment).order_by('order')
        
        if not test_cases.exists():
            submission.status = 'graded'
            submission.total_score = 0
            submission.max_score = 0
            submission.save(update_fields=['status', 'total_score', 'max_score'])
            return {
                "status": "ok",
                "submission_id": submission_id,
                "total_score": 0,
                "max_score": 0,
                "test_results": [],
                "rule_violations": []
            }
        
        # Run test cases
        test_results = []
        total_score = 0
        max_score = 0
        
        for test_case in test_cases:
            max_score += test_case.points_awarded
            
            # Execute code with test input (normalize literal \n from CSV to real newlines)
            input_data = (test_case.input_data or '').replace('\\n', '\n')
            result = execute_code(language, code_str, input_data, submission_id)
            
            # Compare output
            actual_output = result.get('stdout', '').strip()
            expected_output = test_case.expected_output.strip()
            passed = actual_output == expected_output
            
            if passed:
                total_score += test_case.points_awarded
            
            # Create or update TestResult (unique on submission + test_case; re-run overwrites)
            TestResult.objects.update_or_create(
                submission=submission,
                test_case=test_case,
                defaults={
                    'passed': passed,
                    'actual_output': actual_output,
                    'error_message': result.get('stderr', ''),
                    'execution_time': result.get('execution_time', 0.0),
                    'points_earned': test_case.points_awarded if passed else 0,
                },
            )
            
            test_results.append({
                'test_case_id': test_case.id,
                'name': test_case.name,
                'passed': passed,
                'points_earned': test_case.points_awarded if passed else 0,
                'execution_time': result.get('execution_time', 0.0),
                'expected_output': test_case.expected_output,
                'actual_output': actual_output,
                'error_message': result.get('stderr', ''),
                'is_private': getattr(test_case, 'is_private', False),
            })
            
            logger.info(f"Test case {test_case.id} for submission {submission_id}: {'PASS' if passed else 'FAIL'}")
        
        # Check static analysis rules
        rule_violations = []
        try:
            rule_set = RuleSet.objects.get(assignment=assignment)
            violations = check_code_rules(code_str, rule_set, language)
            rule_violations = violations
            
            if violations:
                submission.set_rule_violations(violations)
        except RuleSet.DoesNotExist:
            pass
        except Exception as e:
            logger.error(f"Error checking rules for submission {submission_id}: {e}")
        
        # Update submission with results
        submission.status = 'graded'
        submission.total_score = total_score
        submission.max_score = max_score
        submission.save(update_fields=['status', 'total_score', 'max_score'])
        
        logger.info(f"Grading completed for submission {submission_id}: {total_score}/{max_score}")
        
        return {
            "status": "ok",
            "submission_id": submission_id,
            "total_score": total_score,
            "max_score": max_score,
            "test_results": test_results,
            "rule_violations": rule_violations,
        }
    
    except Exception as e:
        logger.error(f"Grading failed for submission {submission_id}: {e}", exc_info=True)
        submission.status = 'failed'
        submission.save(update_fields=['status'])
        return {
            "status": "error",
            "submission_id": submission_id,
            "error": str(e)
        }


def check_code_rules(code: str, rule_set: RuleSet, language: str) -> list:
    """
    Check student code against static analysis rules.
    
    Args:
        code: Student source code
        rule_set: RuleSet with configured rules
        language: 'python' or 'java'
        
    Returns:
        List of rule violations as dicts with type and message
    """
    violations = []
    
    if language.lower() != 'python':
        # Currently only supports Python AST analysis
        logger.warning(f"Static analysis not supported for language: {language}")
        return violations
    
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        logger.warning(f"Could not parse code for static analysis: {e}")
        return [{
            'type': 'syntax_error',
            'message': f'Syntax error: {e}'
        }]
    
    # Check required functions
    required_functions = rule_set.get_required_functions()
    if required_functions:
        defined_functions = {node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
        for func_name in required_functions:
            if func_name not in defined_functions:
                violations.append({
                    'type': 'missing_function',
                    'message': f'Required function "{func_name}" not found',
                    'function_name': func_name,
                })
    
    # Check forbidden keywords
    forbidden_keywords = rule_set.get_forbidden_keywords()
    if forbidden_keywords:
        for keyword in forbidden_keywords:
            if re.search(r'\b' + re.escape(keyword) + r'\b', code):
                violations.append({
                    'type': 'forbidden_keyword',
                    'message': f'Forbidden keyword "{keyword}" found',
                    'keyword': keyword,
                })
    
    # Check docstrings if required
    if rule_set.requires_docstring:
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                if not ast.get_docstring(node):
                    violations.append({
                        'type': 'missing_docstring',
                        'message': f'Function "{node.name}" missing docstring',
                        'function_name': node.name,
                    })
    
    # Check max function length
    if rule_set.max_function_length and rule_set.max_function_length > 0:
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                func_lines = node.end_lineno - node.lineno if node.end_lineno else 0
                if func_lines > rule_set.max_function_length:
                    violations.append({
                        'type': 'function_too_long',
                        'message': f'Function "{node.name}" is {func_lines} lines (max: {rule_set.max_function_length})',
                        'function_name': node.name,
                        'line_count': func_lines,
                        'max_length': rule_set.max_function_length,
                    })
    
    logger.info(f"Found {len(violations)} rule violations in code")
    return violations
