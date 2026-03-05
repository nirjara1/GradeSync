#!/bin/bash
# GradeSync Local Runner
echo "Starting local GradeSync server..."
cd app && python manage.py runserver
