# Code Review Agent

An autonomous, idempotent GitHub PR Code Review Agent powered by LLMs.
It automatically fetches PR diffs, chunks them semantically, runs parallel analysis across 4 domains (Correctness, Security, Performance, Test Coverage), and posts intelligent inline comments to GitHub via the Review API.

It includes a FastAPI backend, a React live dashboard, and a rich CLI.

## Features
- **Parallel Multi-Domain Analysis**: Runs Correctness, Security, Performance, and Test Coverage in parallel.
- **Semantic Diff Chunking**: Splits large PRs intelligently by function/class boundaries, avoiding split context.
- **Cross-file Synthesis**: Runs a final synthesis pass to catch issues spanning multiple files.
- **Idempotency & Deduplication**: Fingerprints every finding via SHA256 and checks existing PR comments to ensure it never double-posts.
- **Confidence Gating**: Configurable thresholds. `HIGH` confidence posts as a blocking `REQUEST_CHANGES` review. `MEDIUM` posts as suggestions.
- **Suppression Engine**: Repo-specific glob rules to silence known false positives.
- **Live WebSocket Streaming**: Real-time log streaming to the web dashboard.
- **Cost Tracking**: Tracks prompt/completion tokens and estimates USD cost per run.

## Setup

1. **Clone & Install**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r backend/requirements.txt
   
   cd frontend
   npm install
   ```

2. **Configuration**
   Copy `.env.example` to `.env` and fill in your keys:
   ```bash
   cp .env.example .env
   ```
   You need:
   - `GITHUB_TOKEN`: A Personal Access Token with `repo` scope.
   - `OPENAI_API_KEY`: (Or Anthropic/Google depending on `LLM_PROVIDER`).

## Running the Web Dashboard

Start both the backend and frontend development servers.

Terminal 1 (Backend):
```bash
source .venv/bin/activate
python backend/main.py
```
*(Backend runs on http://localhost:8000)*

Terminal 2 (Frontend):
```bash
cd frontend
npm run dev
```
*(Frontend runs on http://localhost:3000)*

## CLI Usage

The CLI is fully featured and includes rich tables and progress streaming.

```bash
source .venv/bin/activate

# Run a review
python cli.py review https://github.com/owner/repo/pull/123

# Dry run (prints findings locally, does not post to GitHub)
python cli.py review https://github.com/owner/repo/pull/123 --dry-run

# Run only specific domains
python cli.py review https://github.com/owner/repo/pull/123 --domains correctness,security

# Change minimum confidence
python cli.py review https://github.com/owner/repo/pull/123 --min-confidence HIGH

# List runs
python cli.py runs list

# Show run details
python cli.py runs show <RUN_ID>
```

## Architecture Notes
- The LLM integration defaults to `gpt-4o-mini` because it is extremely cost-efficient for code review and outputs reliable JSON.
- Diffs are parsed manually to extract exact GitHub diff positions required by the GitHub Comments API.
- The `Deduplicator` uses both cryptographic hashing and keyword-based semantic matching to ensure the same bug is never reported twice, even if line numbers shift in subsequent commits.
