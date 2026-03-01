# GradeSync Autograder AI Module

This is a standalone module for autograding Python and Java submissions, with integrated AI feedback and plagiarism detection.

## Structure

- `runners/`: Docker-based execution runners for Python and Java.
- `scoring/`: Rubric calculation logic.
- `ai/`: Feedback generation, plagiarism detection, and AI likelihood modeling.
- `docker/`: Dockerfiles for the execution environments.

## Setup

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Build Docker images:
   ```bash
   docker build -t gradesync-python -f docker/Dockerfile.python .
   docker build -t gradesync-java -f docker/Dockerfile.java .
   ```

## Usage

### CLI

To run the autograder manually:

```bash
python -m autograder_ai.cli grade --assignment <id> --student <id>
```

### Training AI Model

To train the AI likelihood model:

```bash
python -m autograder_ai.ai.train_ai_likelihood --data_dir data/ai_detection --out ai/models/ai_likelihood.joblib
```
