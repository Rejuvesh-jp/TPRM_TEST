# Research & Technical Decisions: TPRM Assessment Platform

**Feature**: `001-tprm-assessment`
**Date**: 2026-03-09

## Core Architecture: Modular AI Services with RAG

**Decision**: Implement a microservices-based architecture within a modular monolithic codebase.
**Rationale**: Simplifies deployment and development velocity while enforcing strict boundary separation (Principle I).
**Alternatives Considered**: Full microservices (too complex for initial scale), tightly coupled monolith (violates extensibility).

## AI & Data Pipeline Decisions

### 1. Document Processing & Chunking
**Decision**: Use a token-aware sliding window chunking strategy (e.g., 512 tokens with 50-token overlap).
**Rationale**: Ensures context continuity for long documents without losing semantic meaning at boundaries (Principle IV).
**Library**: `langchain` or `llama-index` utility functions for robust PDF/DOCX parsing.

### 2. Embedding Strategy
**Decision**: OpenAI `text-embedding-3-small` (or `large` depending on precision needs).
**Rationale**: High performance, cost-effective for large-scale retrieval.
**Optimization**: Batch embedding requests (up to 2048 chunks) to minimize API round trips (Principle III).

### 3. Vector Storage
**Decision**: PostgreSQL with `pgvector`.
**Rationale**: Unified relational and vector data store simplifies transactions and consistency (Principle VIII). Avoids managing a separate vector DB like Pinecone/Weaviate.
**Index Type**: HNSW (Hierarchical Navigable Small World) for fast approximate nearest neighbor search.

### 4. Asynchronous Execution
**Decision**: Celery + Redis.
**Rationale**: Robust task queue for handling long-running artifact processing and AI analysis without blocking API threads (Principle IX).
**Tasks**: `process_artifact`, `analyze_questionnaire`, `run_gap_analysis`.

## AI Reasoning Strategy

### 5. Multi-Stage Reasoning Pipeline
**Decision**: Sequential execution:
   1. **Extraction**: Parse raw text/tables.
   2. **Retrieval**: Fetch relevant chunks for specific questions.
   3. **Synthesis**: Generate intermediate insights (Concept Extraction).
   4. **Assessment**: Reason over synthesized insights + retrieved context.
**Rationale**: Improves explainability and accuracy compared to single-shot "analyze everything" prompts (Principle V).

### 6. Validation & HITL
**Decision**: Store all AI outputs with `status` flags (`draft`, `pending_review`, `approved`).
**Rationale**: Enables human analysts to intervene at any stage without re-running the entire pipeline (Principle VI).

## Security & Compliance
**Decision**: Vendor-isolated database schemas or row-level security (RLS).
**Rationale**: Strict data isolation is non-negotiable for multi-tenant TPRM systems (Principle X).
**Encryption**: Application-level encryption for sensitive fields before storage.

## Monitoring & Observability
**Decision**: OpenTelemetry instrumentation for traces + structured logging (JSON).
**Rationale**: Critical for debugging complex async AI pipelines (Principle XII).
