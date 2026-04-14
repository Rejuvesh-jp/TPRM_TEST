# Feature Specification: AI-Powered TPRM Assessment Platform

**Feature Branch**: `001-tprm-assessment`
**Created**: 2026-03-09
**Status**: Draft
**Input**: User description: "AI-powered Third Party Risk Management assessment system that analyzes vendor SIG Lite questionnaires, artifacts, policies, and contract clauses to generate risk assessments with recommendations."

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Upload and Analyze Questionnaire (Priority: P1)

A security analyst uploads a vendor's completed SIG Lite questionnaire
(PDF or structured format). The system parses it into sections, questions,
responses, and justifications, then runs AI analysis to produce structured
questionnaire insights including vendor profile summary, control coverage
indicators, weak response flags, and expected artifact references.

**Why this priority**: Questionnaire analysis is the foundational input
for all downstream processing. Without parsed and analyzed questionnaire
data, no gap analysis, risk scoring, or recommendations can be generated.
This is the entry point of every TPRM assessment.

**Independent Test**: Upload a sample SIG Lite questionnaire PDF, trigger
analysis, and verify that structured insights (vendor profile, control
coverage, weak responses) are returned and persisted to the database.

**Acceptance Scenarios**:

1. **Given** a completed SIG Lite questionnaire in PDF format, **When**
   the analyst uploads it via the upload API, **Then** the system stores
   the questionnaire and returns a confirmation with a questionnaire ID.

2. **Given** a stored questionnaire, **When** the analyst triggers
   questionnaire analysis, **Then** the system extracts all sections,
   questions, responses, and justifications into structured records.

3. **Given** extracted questionnaire data, **When** AI analysis completes,
   **Then** the system produces insights including: vendor profile summary,
   control coverage indicators per section, flagged weak responses, and
   expected artifact references for each question.

4. **Given** a questionnaire with missing or vague responses (e.g.,
   "Unknown"), **When** AI analysis runs, **Then** those responses are
   flagged as weak with an explanation of what evidence is expected.

---

### User Story 2 — Upload and Process Vendor Artifacts (Priority: P1)

A security analyst uploads vendor artifacts (individually or as a ZIP
archive containing multiple files). The system extracts text, chunks
documents, generates embeddings, and stores everything. AI then analyzes
artifact content to extract policy coverage, certifications, security
controls, and compliance indicators.

**Why this priority**: Artifact analysis is the second foundational input.
Artifacts provide the evidence base that validates or contradicts
questionnaire responses. Without processed artifacts, gap analysis cannot
cross-reference claims against evidence.

**Independent Test**: Upload a ZIP containing a mix of PDF, DOCX, and TXT
files. Verify that each file is extracted, chunked, embedded, and that
artifact insights are generated and stored.

**Acceptance Scenarios**:

1. **Given** a ZIP archive containing vendor documents, **When** the
   analyst uploads it, **Then** the system unpacks the archive and
   processes each contained file individually.

2. **Given** an uploaded PDF artifact, **When** the processing pipeline
   runs, **Then** the system extracts text, splits it into chunks,
   generates embeddings for each chunk, and stores chunks and embeddings.

3. **Given** processed artifact chunks, **When** AI artifact analysis
   runs, **Then** the system produces artifact insights including: policy
   coverage areas, certifications mentioned, security controls described,
   and compliance indicators.

4. **Given** an unsupported file format inside a ZIP, **When** the system
   encounters it, **Then** it logs a warning, skips the file, and
   continues processing remaining files.

5. **Given** a single artifact upload (not ZIP), **When** the analyst
   uploads a PDF or DOCX, **Then** the system processes it through the
   same pipeline as ZIP-contained files.

---

### User Story 3 — Run Gap Analysis (Priority: P2)

After questionnaire and artifact analysis are complete, the security
analyst triggers gap analysis. The system combines questionnaire insights,
artifact insights, retrieved policy context, and contract clause context
to identify compliance gaps: missing artifacts, unsupported claims, policy
violations, incomplete security controls, and missing contractual
protections.

**Why this priority**: Gap analysis is the core intelligence output that
transforms raw data into actionable findings. It depends on P1 stories
but delivers the primary value proposition of the platform.

**Independent Test**: Given a completed questionnaire analysis and artifact
analysis for the same vendor, trigger gap analysis and verify that
structured gaps are identified with supporting evidence references.

**Acceptance Scenarios**:

1. **Given** completed questionnaire and artifact analysis for a vendor,
   **When** the analyst triggers gap analysis, **Then** the system
   retrieves relevant artifact chunks, policy context, and contract
   clauses using vector similarity search.

2. **Given** a questionnaire response claiming encryption is in place but
   no artifact supports this claim, **When** gap analysis runs, **Then**
   the system identifies a gap: "Encryption claim unsupported by artifact
   evidence" with references to the specific question and search results.

3. **Given** an internal policy requiring annual penetration testing,
   **When** gap analysis compares this against vendor artifacts and
   questionnaire responses, **Then** any missing or insufficient evidence
   is flagged as a policy violation gap.

4. **Given** contract clauses requiring 24-hour incident notification,
   **When** no vendor artifact or questionnaire response addresses incident
   notification timelines, **Then** a contractual misalignment gap is
   identified.

---

### User Story 4 — Generate Risk Assessment (Priority: P2)

After gap analysis is complete, the analyst triggers risk assessment. The
system scores each identified gap with a risk level (Low, Medium, High,
Critical) based on severity, regulatory implications, evidence quality,
and vendor maturity. Each risk includes supporting evidence and recommended
remediation actions.

**Why this priority**: Risk assessment translates gaps into prioritized,
actionable risk findings. It depends on gap analysis but is essential for
the final deliverable.

**Independent Test**: Given a completed gap analysis with multiple gaps,
trigger risk assessment and verify each gap receives a risk level,
supporting evidence, and remediation recommendation.

**Acceptance Scenarios**:

1. **Given** a completed gap analysis with identified gaps, **When** the
   analyst triggers risk assessment, **Then** each gap receives a risk
   level of Low, Medium, High, or Critical.

2. **Given** a gap for missing encryption evidence with regulatory
   implications, **When** risk scoring runs, **Then** the gap is scored
   as High or Critical with an explanation referencing regulatory risk.

3. **Given** a minor gap with available partial evidence, **When** risk
   scoring runs, **Then** the gap is scored as Low or Medium with an
   explanation that partial evidence exists.

4. **Given** a scored risk assessment, **When** the analyst retrieves the
   report, **Then** each risk entry includes: risk level, supporting
   evidence references, and recommended remediation actions.

---

### User Story 5 — Generate Contract Clause Recommendations (Priority: P3)

For each identified gap, the system recommends appropriate contract clauses
that would address the risk. Recommendations are mapped to specific gaps
and include suggested clause language.

**Why this priority**: Contract clause recommendations add significant
value but depend on gap analysis being complete. This is an enhancement
to the core assessment output.

**Independent Test**: Given a gap analysis with identified gaps, verify
that the system generates contract clause recommendations mapped to each
gap with suggested clause text.

**Acceptance Scenarios**:

1. **Given** a gap identifying missing incident response evidence, **When**
   clause recommendation runs, **Then** the system suggests a clause such
   as "Vendor must notify customer of security incidents within 24 hours."

2. **Given** multiple gaps in a vendor assessment, **When** clause
   recommendation runs, **Then** each gap receives at least one
   recommended contract clause with suggested language.

3. **Given** a gap that already has adequate contractual coverage, **When**
   clause recommendation runs, **Then** the system notes that existing
   contract coverage is sufficient and no additional clause is needed.

---

### User Story 6 — Human-in-the-Loop Review (Priority: P3)

Security analysts review AI-generated outputs at key decision points.
They can validate, adjust, override, or reject AI findings for
questionnaire analysis, artifact interpretation, gap analysis, and risk
assessment. All human decisions are recorded with justification.

**Why this priority**: HITL review is critical for enterprise trust and
compliance but can be implemented after the core AI pipeline is functional.
The system produces value even before HITL is fully integrated.

**Independent Test**: Given a completed risk assessment, access the HITL
review endpoint, submit an override for one risk score with justification,
and verify the override is stored and reflected in the assessment.

**Acceptance Scenarios**:

1. **Given** a completed AI risk assessment, **When** the analyst submits
   a HITL review adjusting a risk level from Medium to High, **Then** the
   system stores the override with reviewer identity, timestamp, original
   AI output, modified output, and justification.

2. **Given** a HITL override has been submitted, **When** the assessment
   report is retrieved, **Then** the overridden values are used and the
   original AI values are available for audit.

3. **Given** an analyst reviewing questionnaire analysis, **When** they
   reject an AI interpretation of a response, **Then** the rejection and
   corrected interpretation are stored and used in downstream processing.

---

### User Story 7 — Retrieve Assessment Report (Priority: P2)

The analyst retrieves a complete assessment report for a vendor, combining
questionnaire insights, artifact insights, gap analysis, risk assessment,
contract clause recommendations, and any HITL feedback into a unified
output.

**Why this priority**: The consolidated report is the primary deliverable
of the system. It aggregates all upstream outputs into a single consumable
format.

**Independent Test**: After a full assessment pipeline completes, retrieve
the report and verify it contains all sections with source attribution
and confidence indicators.

**Acceptance Scenarios**:

1. **Given** a fully completed assessment (questionnaire analysis, artifact
   analysis, gap analysis, risk assessment), **When** the analyst requests
   the report, **Then** a structured JSON report is returned containing
   all sections.

2. **Given** a report with AI-generated content, **When** the report is
   retrieved, **Then** every AI conclusion includes source artifact
   references, source questionnaire references, confidence indicators,
   and reasoning explanations.

3. **Given** a partially completed assessment (e.g., artifacts analyzed
   but gap analysis not yet run), **When** the analyst requests the
   report, **Then** completed sections are returned and incomplete
   sections are marked with their current status.

---

### User Story 8 — Embed Policies and Contract Clauses (Priority: P1)

An administrator uploads internal security policies and contract clause
documents. The system extracts text, chunks, generates embeddings, and
stores them for semantic retrieval during gap analysis and clause
recommendation.

**Why this priority**: Policies and contract clauses are foundational
reference data required by gap analysis and clause recommendation. Without
embedded policies, the system cannot evaluate compliance gaps against
internal standards.

**Independent Test**: Upload a set of policy documents and contract clause
documents, then verify they are chunked, embedded, and retrievable via
semantic search.

**Acceptance Scenarios**:

1. **Given** an internal security policy document in PDF format, **When**
   the administrator uploads it, **Then** the system extracts text, chunks
   it, generates embeddings, and stores it as policy reference data.

2. **Given** a contract clause document, **When** the administrator
   uploads it, **Then** the system processes and stores it similarly to
   policies, tagged as contract clause data.

3. **Given** stored policy embeddings, **When** a semantic search query is
   issued (e.g., "encryption requirements"), **Then** the most relevant
   policy chunks are returned ranked by similarity.

---

### Edge Cases

- What happens when an uploaded questionnaire PDF is corrupted or
  unparseable? The system MUST return a clear error indicating the file
  could not be processed and MUST NOT proceed with partial data.

- What happens when a ZIP archive contains nested ZIP files? The system
  MUST extract only the top-level files and log a warning for nested
  archives without processing them.

- What happens when the OpenAI API is unavailable or rate-limited during
  analysis? The system MUST retry with exponential backoff and, after
  exhausting retries, mark the task as failed with a retriable status.

- What happens when a vendor assessment has zero artifacts uploaded? Gap
  analysis MUST still run, flagging all artifact-dependent questions as
  having no supporting evidence.

- What happens when two analysts submit conflicting HITL overrides for the
  same assessment? The most recent override MUST take precedence, and all
  prior overrides MUST be preserved in the audit history.

- What happens when a document contains no extractable text (e.g., a
  scanned image PDF without OCR)? The system MUST flag the artifact as
  unprocessable and note it in the assessment as a gap in evidence.

## Requirements *(mandatory)*

### Functional Requirements

#### Questionnaire Processing

- **FR-001**: System MUST accept SIG Lite questionnaire uploads in PDF
  format and store the raw file with metadata.

- **FR-002**: System MUST parse uploaded questionnaires into structured
  records: sections, questions, responses, and justifications.

- **FR-003**: System MUST run AI analysis on parsed questionnaire data to
  produce structured insights: vendor profile summary, control coverage
  per section, weak response flags, and expected artifact references.

- **FR-004**: System MUST store all questionnaire analysis outputs
  (parsed data and AI insights) in the database.

#### Artifact Processing

- **FR-005**: System MUST accept artifact uploads as individual files or
  ZIP archives containing multiple files.

- **FR-006**: System MUST support at minimum: PDF, DOCX, TXT, CSV, XLSX,
  and JSON file formats for artifact processing.

- **FR-007**: System MUST extract text from uploaded artifacts and split
  it into semantic chunks.

- **FR-008**: System MUST generate embeddings for each artifact chunk and
  store them in the vector database.

- **FR-009**: System MUST run AI analysis on artifact content to extract
  insights: policy coverage, certifications, security controls, and
  compliance indicators.

- **FR-010**: System MUST store all artifact chunks, embeddings, and
  insights in the database.

#### Policy and Contract Processing

- **FR-011**: System MUST accept internal policy document uploads and
  process them through the same text extraction, chunking, and embedding
  pipeline as artifacts.

- **FR-012**: System MUST accept contract clause document uploads and
  process them through the same pipeline, tagged as contract clause data.

- **FR-013**: System MUST support semantic retrieval of policy and contract
  clause chunks using vector similarity search.

#### Gap Analysis

- **FR-014**: System MUST combine questionnaire insights, artifact
  insights, retrieved policy context, and contract clause context to
  identify compliance gaps.

- **FR-015**: System MUST identify the following gap types: missing
  artifacts, unsupported questionnaire claims, policy violations,
  incomplete security controls, and missing contractual protections.

- **FR-016**: Each identified gap MUST include references to the source
  questionnaire responses, artifact chunks, and policy sections that
  contributed to the finding.

- **FR-017**: System MUST use vector similarity search to retrieve
  relevant artifact, policy, and contract clause chunks during gap
  analysis.

#### Risk Assessment

- **FR-018**: System MUST assign a risk level (Low, Medium, High, or
  Critical) to each identified gap.

- **FR-019**: Risk scoring MUST consider: severity of missing controls,
  regulatory implications, lack of supporting evidence, and vendor
  maturity indicators.

- **FR-020**: Each risk entry MUST include: risk level, supporting
  evidence references, and recommended remediation actions.

#### Contract Clause Recommendations

- **FR-021**: System MUST generate contract clause recommendations for
  each identified gap where contractual remediation is applicable.

- **FR-022**: Each recommendation MUST include suggested clause language
  mapped to the specific gap it addresses.

#### Reasoning Validation

- **FR-023**: System MUST validate final assessments for consistency
  between questionnaire responses and artifact evidence.

- **FR-024**: System MUST verify adequacy of evidence supporting each
  conclusion and logical correctness of risk scoring.

#### Human-in-the-Loop

- **FR-025**: System MUST allow authorized reviewers to validate, adjust,
  or override AI outputs at these decision points: questionnaire analysis,
  artifact interpretation, gap analysis, and risk assessment.

- **FR-026**: All human overrides MUST be recorded with: reviewer identity,
  timestamp, original AI output, modified output, and justification.

- **FR-027**: Human-validated outputs MUST take precedence over AI-generated
  outputs in all downstream processing.

#### Reporting

- **FR-028**: System MUST generate a consolidated assessment report
  containing: questionnaire insights, artifact insights, gap analysis,
  risk assessment, contract clause recommendations, and HITL feedback.

- **FR-029**: Every AI-generated conclusion in the report MUST include:
  source artifact references, source questionnaire references, confidence
  indicators, and explanation of reasoning.

#### API

- **FR-030**: System MUST expose REST APIs for: uploading questionnaires,
  uploading artifacts, starting analysis, retrieving insights, retrieving
  gap analysis, retrieving risk assessment, and submitting HITL feedback.

- **FR-031**: All long-running operations MUST support asynchronous
  processing with status polling.

#### Data Persistence

- **FR-032**: All intermediate and final outputs MUST be stored in the
  database. In-memory-only storage for assessment data is prohibited.

- **FR-033**: Every persisted record MUST include created and updated
  timestamps and a reference to the assessment run.

#### Security

- **FR-034**: System MUST enforce role-based access control on all API
  endpoints.

- **FR-035**: System MUST log all AI interactions (prompts, responses,
  token usage) for traceability.

- **FR-036**: System MUST isolate vendor data such that one vendor's data
  is not accessible during another vendor's assessment.

### Key Entities

- **Vendor**: The third party being assessed. Has a name, identifier, and
  status. Linked to one or more assessments.

- **Assessment**: A single evaluation run for a vendor. Tracks status
  (in-progress, completed, reviewed). Links to all analysis outputs.

- **Questionnaire**: The uploaded SIG Lite questionnaire file and its
  parsed content. Belongs to an assessment.

- **Question**: An individual question extracted from a questionnaire.
  Includes section, question text, response, and justification. Grouped
  by section.

- **Artifact**: A vendor-uploaded document. Has file metadata, processing
  status, and links to its chunks and insights.

- **ArtifactChunk**: A segment of extracted text from an artifact. Linked
  to its parent artifact and its embedding.

- **Embedding**: A vector representation of a text chunk (artifact, policy,
  or contract clause). Stored via pgvector for similarity search.

- **Policy**: An internal security policy document. Processed into chunks
  and embeddings for retrieval.

- **ContractClause**: A contract clause document or individual clause.
  Processed into chunks and embeddings for retrieval.

- **GapAssessment**: An identified compliance gap. Includes gap type,
  description, source references, and linked risk assessment.

- **RiskAssessment**: A scored risk entry. Includes risk level, supporting
  evidence, recommended remediation, and optional HITL override.

- **Recommendation**: A suggested contract clause. Mapped to a specific
  gap with suggested clause language.

- **HITLFeedback**: A human review decision. Records reviewer, timestamp,
  original AI output, modified output, and justification.

- **QuestionnaireInsight**: AI-generated analysis output for the
  questionnaire. Includes vendor profile, control coverage, and flags.

- **ArtifactInsight**: AI-generated analysis output for an artifact.
  Includes policy coverage, certifications, controls, and compliance
  indicators.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The system can ingest a SIG Lite questionnaire and produce
  structured insights within 60 seconds for a standard-length
  questionnaire (approximately 200 questions).

- **SC-002**: Artifact processing completes within 30 seconds per document
  for files up to 50 pages, including text extraction, chunking, embedding
  generation, and insight extraction.

- **SC-003**: Gap analysis identifies at least 90% of gaps that a human
  security analyst would identify when given the same inputs (measured
  against a curated benchmark set).

- **SC-004**: Every AI-generated finding in the assessment report includes
  traceable source references (artifact, questionnaire, or policy) such
  that an auditor can verify the basis for each conclusion.

- **SC-005**: The system supports processing assessments for 10 or more
  vendors concurrently without performance degradation beyond 20% of
  single-vendor processing time.

- **SC-006**: Security analysts can complete a full HITL review (validate,
  adjust, override) of an AI-generated assessment within 30 minutes for a
  typical vendor with 5–10 artifacts and a standard SIG Lite questionnaire.

- **SC-007**: Risk scoring consistency: given the same inputs run twice,
  the system produces identical risk levels and gap identifications
  (deterministic when using the same model and parameters).

- **SC-008**: The consolidated assessment report contains all required
  sections (questionnaire insights, artifact insights, gaps, risks,
  recommendations, HITL feedback) with zero missing source attributions.

### Assumptions

- The SIG Lite questionnaire follows a consistent structure (section →
  question → response → justification) across vendors.

- Vendor artifacts are text-extractable (not scanned images without OCR).
  Scanned-image-only PDFs are flagged as unprocessable rather than
  silently ignored.

- Internal policies and contract clauses are uploaded before assessments
  are run. The system does not ship with pre-loaded policy content.

- Role-based access control uses the enterprise's existing identity
  provider. The system integrates with it rather than managing its own
  user directory.

- The embedding model produces vectors of a consistent dimensionality
  across all document types (artifacts, policies, contract clauses).

- A "standard" SIG Lite questionnaire contains approximately 100–300
  questions grouped into 15–20 sections.
