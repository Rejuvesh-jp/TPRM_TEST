# AI-Powered TPRM Assessment System

This project automates Third Party Risk Management (TPRM) assessments by analyzing SIG Lite questionnaires using RAG and LLMs.

## Prerequisites

- Python 3.11+
- PostgreSQL 15+ (with `pgvector` extension)
- Redis (for Celery)

## Local Setup (Windows)

Since Docker is not available in your environment, follow these steps:

1. **Install Python Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Database Setup**:
   You must install the `pgvector` extension manually. See [docs/windows-setup.md](docs/windows-setup.md) for detailed instructions.
   Once installed, run this SQL command:
   ```sql
   CREATE EXTENSION IF NOT EXISTS vector;
   ```

3. **Environment**:
   Copy `.env.example` to `.env` and fill in your OpenAI API key and database credentials.

## Documentation

- [Project Specification](specs/001-tprm-assessment/spec.md)
- [Implementation Plan](specs/001-tprm-assessment/plan.md)
- [Data Model](specs/001-tprm-assessment/data-model.md)
