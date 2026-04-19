from concurrent.futures import ThreadPoolExecutor, as_completed

from celery import shared_task
from django.core.mail import send_mail
from django.conf import settings
from django.db import close_old_connections, connection
from django.utils import timezone
from grading.models import Assignment, Submission, Student
from grading.services import grade_submission
from grading.group_services import get_effective_submission_for_student
import logging

logger = logging.getLogger(__name__)


def _grade_submission_thread_safe(submission_id: int) -> tuple:
    """Run autograde in a worker thread; Django requires per-thread DB hygiene."""
    close_old_connections()
    try:
        grade_submission(submission_id)
        return True, submission_id, None
    except Exception as exc:
        logger.error("Error grading submission %s: %s", submission_id, exc, exc_info=True)
        return False, submission_id, str(exc)
    finally:
        close_old_connections()


@shared_task(bind=True, max_retries=3)
def bulk_grade_assignment(self, assignment_id):
    """
    Asynchronously grade all submissions for an assignment.
    
    Args:
        assignment_id: ID of the assignment to grade
        
    Returns:
        Dictionary with grading results summary
    """
    try:
        assignment = Assignment.objects.get(id=assignment_id)
    except Assignment.DoesNotExist:
        logger.error(f"Assignment {assignment_id} not found")
        return {'status': 'error', 'message': 'Assignment not found'}
    
    try:
        # Get all students in the course
        students = list(
            Student.objects.filter(
                user__course_memberships__course=assignment.course,
                user__course_memberships__role_in_course='STUDENT',
            ).select_related('user')
        )

        total_students = len(students)
        graded_count = 0
        failed_count = 0
        missing_submissions = []
        submission_ids = []
        for student in students:
            submission = get_effective_submission_for_student(assignment, student)
            if submission is None:
                missing_submissions.append(
                    {
                        'student_id': student.id,
                        'student_name': student.user.get_full_name() or student.user.username,
                        'email': student.user.email,
                    }
                )
                continue
            submission_ids.append(submission.id)

        use_parallel = connection.vendor == 'postgresql' and len(submission_ids) > 1
        processed = 0

        def _emit_progress():
            self.update_state(
                state='PROGRESS',
                meta={
                    'current': processed,
                    'total': total_students,
                    'graded': graded_count,
                    'failed': failed_count,
                },
            )

        if use_parallel:
            workers = min(4, len(submission_ids))
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = {pool.submit(_grade_submission_thread_safe, sid): sid for sid in submission_ids}
                for fut in as_completed(futures):
                    ok, sid, _err = fut.result()
                    processed += 1
                    if ok:
                        graded_count += 1
                    else:
                        failed_count += 1
                    if processed % 3 == 0 or processed == len(submission_ids):
                        _emit_progress()
        else:
            for submission_id in submission_ids:
                try:
                    grade_submission(submission_id)
                    graded_count += 1
                except Exception as e:
                    failed_count += 1
                    logger.error("Error grading submission %s: %s", submission_id, e, exc_info=True)
                processed += 1
                if processed % 3 == 0 or processed == len(submission_ids):
                    _emit_progress()
        
        # Calculate statistics
        results = {
            'status': 'success',
            'assignment_id': assignment_id,
            'assignment_name': assignment.name,
            'total_students': total_students,
            'graded': graded_count,
            'failed': failed_count,
            'missing_submissions': len(missing_submissions),
            'missing_students': missing_submissions,
            'completed_at': timezone.now().isoformat(),
        }
        
        # Send completion notification
        try:
            notify_bulk_grading_complete(
                assignment,
                results,
                instructor=assignment.course.professor
            )
        except Exception as e:
            logger.error(f"Error sending notification: {str(e)}")
        
        logger.info(f"Completed bulk grading for assignment {assignment_id}: {results}")
        return results
        
    except Exception as exc:
        logger.error(f"Unexpected error in bulk_grade_assignment: {str(exc)}")
        # Retry with exponential backoff
        raise self.retry(exc=exc, countdown=60 * (self.request.retries + 1))


@shared_task(bind=True, max_retries=2)
def grade_submission_async(self, submission_id):
    """
    Asynchronously grade a single submission.
    
    Args:
        submission_id: ID of the submission to grade
        
    Returns:
        Dictionary with grading result
    """
    try:
        submission = Submission.objects.get(id=submission_id)
    except Submission.DoesNotExist:
        logger.error(f"Submission {submission_id} not found")
        return {'status': 'error', 'message': 'Submission not found'}
    
    try:
        # Mark as grading
        submission.status = 'grading'
        submission.save()
        
        # Execute grading
        result = grade_submission(submission_id)
        
        logger.info(f"Completed grading for submission {submission_id}")
        return {
            'status': 'success',
            'submission_id': submission_id,
            'score': submission.total_score,
            'max_score': submission.max_score
        }
        
    except Exception as exc:
        logger.error(f"Error grading submission {submission_id}: {str(exc)}")
        submission.status = 'failed'
        submission.save()
        raise self.retry(exc=exc, countdown=30 * (self.request.retries + 1))


@shared_task(bind=True, max_retries=2)
def run_submission_analysis_async(self, submission_id):
    """
    Asynchronously run AI likelihood and Plagiarism checks on a submission.
    Ensures that when a student submits, the analysis is there by the time the instructor opens it.
    """
    try:
        from grading.services import run_submission_analysis
        
        logger.info(f"Starting background Integrity Analysis for submission {submission_id}")
        return run_submission_analysis(submission_id)
    except Exception as exc:
        logger.error(f"Error in background Integrity Analysis for submission {submission_id}: {str(exc)}")
        raise self.retry(exc=exc, countdown=30 * (self.request.retries + 1))


@shared_task
def cleanup_old_results():
    """
    Clean up old Celery task results from the result backend.
    Runs periodically (e.g., hourly).
    """
    try:
        from django_celery_results.models import TaskResult
        from datetime import timedelta
        
        # Delete results older than 24 hours
        cutoff_time = timezone.now() - timedelta(hours=24)
        deleted_count, _ = TaskResult.objects.filter(
            date_done__lt=cutoff_time
        ).delete()
        
        logger.info(f"Cleaned up {deleted_count} old task results")
        return {'status': 'success', 'deleted': deleted_count}
        
    except ImportError:
        logger.debug("django-celery-results not installed, skipping cleanup")
        return {'status': 'skipped', 'reason': 'django-celery-results not installed'}


def notify_bulk_grading_complete(assignment, results, instructor):
    """
    Send notification when bulk grading is complete.
    
    Args:
        assignment: Assignment object
        results: Dictionary with grading results
        instructor: User object of the instructor
    """
    subject = f"GradeSync: Bulk grading complete for {assignment.name}"
    
    message = f"""
Bulk grading has been completed for "{assignment.name}".

Summary:
--------
Total Students: {results['total_students']}
Successfully Graded: {results['graded']}
Failed: {results['failed']}
Missing Submissions: {results['missing_submissions']}
Completed At: {results['completed_at']}

Missing Submissions:
"""
    
    if results['missing_students']:
        for student in results['missing_students'][:10]:  # Show first 10
            message += f"\n- {student['student_name']} ({student['email']})"
        if len(results['missing_students']) > 10:
            message += f"\n... and {len(results['missing_students']) - 10} more"
    else:
        message += "\nNone"
    
    message += f"""

Log in to GradeSync to review the detailed grade report:
{settings.SITE_URL}/grading/assignments/{assignment.id}/grade-report/
"""
    
    try:
        send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            [instructor.email],
            fail_silently=True
        )
    except Exception as e:
        logger.error(f"Failed to send bulk grading notification: {str(e)}")
