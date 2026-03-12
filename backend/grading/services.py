import os
import io
import zipfile
import logging
from django.conf import settings
from .models import Submission
from autograder_ai.ai.inference_ai_likelihood import AIInferenceEngine
from autograder_ai.ai.similarity import SimilarityEngine

logger = logging.getLogger(__name__)

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
            model_path = os.path.join(settings.BASE_DIR.parent, 'autograder_ai', 'ai', 'models', 'rf_model.pkl')
            ai_engine = AIInferenceEngine(model_path)
            
            likelihood_pct, conf_pct, explanation = ai_engine.predict_with_confidence(code_str)
            
            submission.ai_likelihood_score = likelihood_pct
            submission.ai_confidence_score = conf_pct
            submission.ai_explanation = explanation
            logger.info(f"AI score for submission {submission_id}: {submission.ai_likelihood_score}")
        except Exception as e:
            logger.error(f"AI Inference failed for submission {submission_id}: {e}")
            submission.ai_likelihood_score = None
            submission.ai_confidence_score = None
            submission.ai_explanation = "AI analysis unavailable."

        # 2. Plagiarism Detection
        try:
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
