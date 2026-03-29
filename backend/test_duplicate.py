import os
import django
import sys
import json

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.test import Client
from django.contrib.auth.models import User
from professor.models import Course, UserProfile
from grading.models import Assignment, TestCase

def run_test():
    # Setup test user and course
    user, _ = User.objects.get_or_create(username='test_prof')
    user.set_password('password123')
    user.save()
    
    profile, _ = UserProfile.objects.get_or_create(user=user, defaults={'role': 'FACULTY'})
    profile.role = 'FACULTY'
    profile.save()
    
    course, _ = Course.objects.get_or_create(name='Test Course', professor=user)
    
    # Client login
    client = Client()
    client.login(username='test_prof', password='password123')
    
    # Create Assignment with test cases
    test_cases_data = [
        {"input_data": "1", "expected_output": "2", "is_private": False, "points": 5},
        {"input_data": "2", "expected_output": "4", "is_private": True, "points": 5}
    ]
    
    post_data = {
        'name': 'Test Assignment',
        'description': 'Description',
        'points': '10',
        'allowed_language': 'python',
        'test_cases_json': json.dumps(test_cases_data),
        'status': 'published'
    }
    
    response = client.post(f'/assignments/course/{course.id}/create/', post_data)
    
    assignment = Assignment.objects.filter(name='Test Assignment').last()
    print(f"Created Assignment '{assignment.name}'")
    
    test_cases = TestCase.objects.filter(assignment=assignment).order_by('id')
    print(f"Total test cases on create: {test_cases.count()}")
    for tc in test_cases:
        print(f"  - {tc.name} [private: {tc.is_private}]")
        
    print("\nSimulating Edit Assignment (NO new CSV)...")
    response = client.post(f'/assignments/{assignment.id}/edit/', post_data)
    
    test_cases = TestCase.objects.filter(assignment=assignment).order_by('id')
    print(f"Total test cases on edit: {test_cases.count()}")
    for tc in test_cases:
        print(f"  - {tc.name} [private: {tc.is_private}]")

if __name__ == '__main__':
    run_test()
