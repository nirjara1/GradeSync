import argparse
import os
import json
from .schemas import GradeRequest
from .service import GradingService

def main():
    parser = argparse.ArgumentParser(description="GradeSync Autograder CLI")
    subparsers = parser.add_subparsers(dest='command', help='Commands')
    
    # Grade Command
    grade_parser = subparsers.add_parser('grade', help='Grade a submission')
    grade_parser.add_argument('--assignment', required=True, help='Assignment ID')
    grade_parser.add_argument('--student', required=True, help='Student ID')
    grade_parser.add_argument('--language', default='python', help='Language (python/java)')
    grade_parser.add_argument('--submission', help='Path to submission dir (default: autograder_ai/submissions/<assignment>/<student>)')
    grade_parser.add_argument('--config', help='Path to assignment config (default: autograder_ai/assignments/<assignment>/config.json)')
    
    args = parser.parse_args()
    
    if args.command == 'grade':
        # Defaults
        base_dir = os.getcwd()
        submission_path = args.submission or os.path.join(base_dir, "autograder_ai/submissions", args.assignment, args.student)
        config_path = args.config or os.path.join(base_dir, "autograder_ai/assignments", args.assignment, "config.json")
        
        request = GradeRequest(
            assignment_id=args.assignment,
            student_id=args.student,
            language=args.language,
            submission_path=submission_path,
            assignment_config_path=config_path
        )
        
        service = GradingService()
        response = service.grade_submission(request)
        
        print(json.dumps(json.loads(response.model_dump_json()), indent=2))

if __name__ == "__main__":
    main()
