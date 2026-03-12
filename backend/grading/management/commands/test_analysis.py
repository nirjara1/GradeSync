import io
import zipfile
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from grading.models import Submission, Assignment
from grading.services import run_submission_analysis
from django.core.files.base import ContentFile

class Command(BaseCommand):
    help = 'Tests the AI and Plagiarism analysis pipeline by simulating file submissions.'

    def handle(self, *args, **options):
        try:
            student = User.objects.get(username='student@warhawks.ulm.edu')
            assignment = Assignment.objects.first()
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Prerequisites not found: {e}"))
            return

        self.stdout.write(self.style.WARNING('\n--- Testing Python submission ---'))
        sub_py, _ = Submission.objects.get_or_create(
            assignment=assignment,
            student=student.student_profile
        )
        
        # Override file to test proper saving and run extraction
        sub_py.file_path.save('test_sub.py', ContentFile(b'def hello():\n    print("world")'))
        sub_py.save()

        result_py = run_submission_analysis(sub_py.id)
        self.stdout.write(self.style.SUCCESS(f"PY Analysis Result: {result_py}"))

        self.stdout.write(self.style.WARNING('\n--- Testing ZIP submission ---'))
        assignment2 = Assignment.objects.last()
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w') as zf:
            zf.writestr('main.py', b'def zip_hello():\n    print("zip world")')
        zip_buffer.seek(0)

        sub_zip, _ = Submission.objects.get_or_create(
            assignment=assignment2,
            student=student.student_profile
        )
        
        # Override file to test zip extraction
        sub_zip.file_path.save('test_sub.zip', ContentFile(zip_buffer.read()))
        sub_zip.save()

        result_zip = run_submission_analysis(sub_zip.id)
        self.stdout.write(self.style.SUCCESS(f"ZIP Analysis Result: {result_zip}"))

        self.stdout.write(self.style.SUCCESS('\nAll tests completed.'))
