#!/bin/bash
# GradeSync Local Runner
echo "Starting local GradeSync server..."
cd backend && python3 manage.py runserver
