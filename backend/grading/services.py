import os
import io
import zipfile
import logging
import ast
import re
from django.conf import settings
from django.db import transaction
from .models import Submission, TestCase, TestResult, RuleSet, Assignment
from .sandbox import execute_code

logger = logging.getLogger(__name__)


def _submission_owner_label(submission: Submission) -> str:
    if submission.student_id and submission.student and submission.student.user:
        return submission.student.user.email or submission.student.user.username
    if submission.group_id:
        member = submission.group.members.select_related('student__user').first()
        if member and member.student and member.student.user:
            return member.student.user.email or member.student.user.username
        return f"group-{submission.group_id}"
    return f"submission-{submission.id}"

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
    Runs AI detection and Plagiarism detection on a single submission safely.
    """
    try:
        with transaction.atomic():
            submission = Submission.objects.select_for_update().select_related('assignment', 'student__user').get(id=submission_id)
            logger.info(f"Starting atomic analysis for submission {submission_id}")

            code_str, file_count = extract_code_from_file(submission.file_path)
            logger.info(f"Extracted {file_count} source files from submission {submission_id}")
            
            if not code_str.strip():
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
                return {"status": "skipped", "submission_id": submission_id, "reason": "No valid source code"}

            try:
                from admin_dashboard.models import SystemSettings

                sys_settings = SystemSettings.load()
            except Exception:
                sys_settings = None
            ai_enabled = sys_settings is None or sys_settings.ai_code_detection_enabled
            plag_enabled = sys_settings is None or sys_settings.plagiarism_detection_enabled

            # 1. AI Detection
            try:
                if not ai_enabled:
                    submission.ai_likelihood_score = None
                    submission.ai_confidence_score = None
                    submission.ai_explanation = "AI code detection disabled by institution settings."
                elif HAS_AI_MODULES:
                    model_dir = os.path.join(settings.BASE_DIR.parent, 'autograder_ai', 'ai', 'models')
                    model_path = os.path.join(model_dir, 'rf_model.pkl')
                    logger.info(f"Searching for AI model at: {model_path}")
                    if os.path.exists(model_path):
                        ai_engine = AIInferenceEngine(model_path)
                        likelihood_pct, conf_pct, explanation = ai_engine.predict_with_confidence(code_str)
                        submission.ai_likelihood_score = likelihood_pct
                        submission.ai_confidence_score = conf_pct
                        submission.ai_explanation = explanation
                        logger.info(f"AI Detection Result: {likelihood_pct}% (confidence {conf_pct}%)")
                    else:
                        logger.warning(f"AI Model not found at {model_path}")
                        submission.ai_likelihood_score = None
                        submission.ai_confidence_score = None
                        submission.ai_explanation = "AI analysis unavailable (model error)."
                else:
                    submission.ai_likelihood_score = None
                    submission.ai_confidence_score = None
                    submission.ai_explanation = "AI analysis unavailable (modules missing)."
            except Exception as e:
                logger.error(f"AI Inference failed for submission {submission_id}: {e}")
                submission.ai_likelihood_score = None
                submission.ai_confidence_score = None
                submission.ai_explanation = "AI analysis unavailable (model error)."

            # 2. Plagiarism Detection
            try:
                if not plag_enabled:
                    submission.plagiarism_score = None
                    submission.plagiarism_confidence_score = None
                    submission.plagiarism_match_info = "Plagiarism detection disabled by institution settings."
                    submission.plagiarism_match = None
                elif HAS_AI_MODULES:
                    other_submissions = Submission.objects.filter(assignment=submission.assignment).exclude(id=submission.id)
                    logger.info(f"Checking similarity against {other_submissions.count()} other submissions")
                    
                    corpus_texts = {}
                    for other_sub in other_submissions:
                        other_code, other_file_count = extract_code_from_file(other_sub.file_path)
                        if other_code.strip():
                            corpus_texts[str(other_sub.id)] = other_code
                        else:
                            logger.warning(f"Corpus submission {other_sub.id} has no extractable code (files: {other_file_count})")
                            
                    sim_engine = SimilarityEngine(n=3)
                    sim_results = sim_engine.check_similarity_from_texts(code_str, corpus_texts)
                    
                    if sim_results:
                        top_match_id, sim_score = sim_results[0]
                        submission.plagiarism_score = round(sim_score * 100, 1)
                        if sim_score > 0.7:
                            confidence = 98.0
                        else:
                            confidence = round(80.0 + (sim_score * 15.0), 1)
                        submission.plagiarism_confidence_score = min(confidence, 100.0)
                        
                        try:
                            matched_sub = Submission.objects.get(id=int(top_match_id))
                            submission.plagiarism_match = matched_sub
                            email = _submission_owner_label(matched_sub)
                            submission.plagiarism_match_info = f"Closest Match: {email}"
                            
                            current_matched_score = matched_sub.plagiarism_score or 0.0
                            if submission.plagiarism_score > current_matched_score:
                                matched_sub.plagiarism_score = submission.plagiarism_score
                                matched_sub.plagiarism_confidence_score = submission.plagiarism_confidence_score
                                matched_sub.plagiarism_match = submission
                                sub_email = _submission_owner_label(submission)
                                matched_sub.plagiarism_match_info = f"Closest Match: {sub_email}"
                                matched_sub.save(update_fields=[
                                    'plagiarism_score', 'plagiarism_confidence_score',
                                    'plagiarism_match_info', 'plagiarism_match'
                                ])
                        except (Submission.DoesNotExist, ValueError):
                            submission.plagiarism_match = None
                            submission.plagiarism_match_info = "Closest Match: Unknown"
                    else:
                        submission.plagiarism_score = 0.0
                        submission.plagiarism_confidence_score = 95.0
                        submission.plagiarism_match = None
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
                'plagiarism_score', 'plagiarism_confidence_score', 'plagiarism_match_info',
                'plagiarism_match'
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
                "plagiarism_match_id": submission.plagiarism_match_id,
                "num_files_analyzed": file_count
            }
    except Exception as e:
        logger.error(f"Overall analysis failed for submission {submission_id}: {e}")
        return {
            "status": "error",
            "submission_id": submission_id,
            "error": str(e)
        }


def run_bulk_plagiarism_analysis(assignment_id: int) -> dict:
    """
    Efficiently re-analyses plagiarism for every submission in an assignment.

    Strategy
    --------
    1. Fetch all submissions in a SINGLE query.
    2. Pre-compute Winnowing fingerprints (frozenset[int]) for every file ONCE.
       Fingerprint generation is O(N); comparing integer sets is ~1 000× faster
       than comparing string n-gram sets.
    3. Run the O(N²) upper-triangle comparison using containment similarity.
    4. Wrap ALL database writes in a single transaction.atomic() + bulk_update
       so we hit the database ONCE instead of N times.

    Returns a summary dict: {status, total, updated, skipped, errors}
    """
    if not HAS_AI_MODULES:
        return {"status": "error", "reason": "AI modules not available"}

    try:
        from admin_dashboard.models import SystemSettings

        if not SystemSettings.load().plagiarism_detection_enabled:
            return {"status": "skipped", "reason": "Plagiarism detection disabled in system settings"}
    except Exception:
        pass

    try:
        assignment = Assignment.objects.get(id=assignment_id)
    except Assignment.DoesNotExist:
        return {"status": "error", "reason": f"Assignment {assignment_id} not found"}

    # --- Single query: fetch everything we need up-front ---
    submissions = list(
        Submission.objects.filter(assignment=assignment)
        .select_related('student__user', 'group')
    )

    logger.info(
        f"[bulk_plagiarism] Starting analysis for assignment {assignment_id} "
        f"– {len(submissions)} submissions"
    )

    # --- Step 1: Extract code once per submission ---
    corpus: dict[str, str] = {}        # id_str → raw code
    sub_map: dict[str, Submission] = {}
    skipped = 0

    for sub in submissions:
        code, _n = extract_code_from_file(sub.file_path)
        if code.strip():
            corpus[str(sub.id)] = code
            sub_map[str(sub.id)] = sub
        else:
            skipped += 1
            logger.warning(
                f"[bulk_plagiarism] Submission {sub.id} has no extractable code – skipping"
            )

    if len(corpus) < 2:
        logger.info("[bulk_plagiarism] Not enough valid submissions to compare")
        return {
            "status": "ok",
            "total": len(submissions),
            "updated": 0,
            "skipped": skipped,
            "errors": 0,
        }

    # --- Step 2: Pre-compute Winnowing fingerprints (integer sets) – O(N) ---
    engine = SimilarityEngine()   # k=25, w=4 (MOSS defaults)
    fingerprints: dict[str, frozenset] = {}
    for sid, code in corpus.items():
        try:
            fingerprints[sid] = engine.fingerprint(code)
        except Exception as exc:
            logger.error(f"[bulk_plagiarism] Fingerprint failed for {sid}: {exc}")
            fingerprints[sid] = frozenset()

    logger.info(f"[bulk_plagiarism] Fingerprinted {len(fingerprints)} submissions")

    # --- Step 3: O(N²) upper-triangle comparison on integer sets ---
    ids = list(fingerprints.keys())
    pair_scores: dict[tuple, float] = {}   # (a, b) → containment score

    for i in range(len(ids)):
        fp_a = fingerprints[ids[i]]
        if not fp_a:
            continue
        for j in range(i + 1, len(ids)):
            fp_b = fingerprints[ids[j]]
            if not fp_b:
                continue
            intersection = len(fp_a & fp_b)
            score = intersection / min(len(fp_a), len(fp_b))
            if score > 0.05:
                pair_scores[(ids[i], ids[j])] = score

    # Build per-submission top-match from the pair table
    best_match: dict[str, tuple] = {}   # sid → (matched_sid, score)
    for (a, b), score in pair_scores.items():
        if a not in best_match or score > best_match[a][1]:
            best_match[a] = (b, score)
        if b not in best_match or score > best_match[b][1]:
            best_match[b] = (a, score)

    # --- Step 4: Populate model fields, then bulk_update in ONE transaction ---
    to_update: list[Submission] = []
    errors = 0

    for sid_str, sub in sub_map.items():
        try:
            if sid_str in best_match:
                top_id_str, score = best_match[sid_str]
                sub.plagiarism_score = round(score * 100, 1)
                sub.plagiarism_confidence_score = (
                    98.0 if score > 0.7
                    else min(round(80.0 + score * 15.0, 1), 100.0)
                )
                matched_sub = sub_map.get(top_id_str)
                if matched_sub:
                    sub.plagiarism_match = matched_sub
                    sub.plagiarism_match_info = (
                        f"Closest Match: {_submission_owner_label(matched_sub)}"
                    )
                else:
                    sub.plagiarism_match = None
                    sub.plagiarism_match_info = "Closest Match: Unknown"
            else:
                sub.plagiarism_score = 0.0
                sub.plagiarism_confidence_score = 95.0
                sub.plagiarism_match = None
                sub.plagiarism_match_info = "No significant similarities found."

            to_update.append(sub)
            logger.info(f"[bulk_plagiarism] Submission {sid_str}: {sub.plagiarism_score}%")
        except Exception as exc:
            errors += 1
            logger.error(f"[bulk_plagiarism] Failed to prepare submission {sid_str}: {exc}")

    # Single atomic write – N times fewer DB round-trips
    update_fields = [
        'plagiarism_score', 'plagiarism_confidence_score',
        'plagiarism_match_info', 'plagiarism_match',
    ]
    try:
        with transaction.atomic():
            Submission.objects.bulk_update(to_update, update_fields)
        updated = len(to_update)
        logger.info(f"[bulk_plagiarism] bulk_update wrote {updated} rows in one transaction")
    except Exception as exc:
        logger.error(f"[bulk_plagiarism] bulk_update failed: {exc}")
        errors += len(to_update)
        updated = 0

    return {
        "status": "ok",
        "assignment_id": assignment_id,
        "total": len(submissions),
        "updated": updated,
        "skipped": skipped,
        "errors": errors,
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
            max_score += 1
            
            # Execute code with test input (normalize literal \n from CSV to real newlines)
            input_data = (test_case.input_data or '').replace('\\n', '\n')
            result = execute_code(language, code_str, input_data, submission_id)
            
            # Compare output
            actual_output = result.get('stdout', '').strip()
            expected_output = test_case.expected_output.strip()
            passed = actual_output == expected_output
            
            if passed:
                total_score += 1
            
            # Create or update TestResult (unique on submission + test_case; re-run overwrites)
            TestResult.objects.update_or_create(
                submission=submission,
                test_case=test_case,
                defaults={
                    'passed': passed,
                    'actual_output': actual_output,
                    'error_message': result.get('stderr', ''),
                    'execution_time': result.get('execution_time', 0.0),
                    'points_earned': 1 if passed else 0,
                },
            )
            
            test_results.append({
                'test_case_id': test_case.id,
                'name': test_case.name,
                'passed': passed,
                'points_earned': 1 if passed else 0,
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
