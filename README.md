
<div align="center">

<img src="docs/images/hindsight-banner.png" alt="Hindsight — Agent Memory That Learns" width="100%"/>

# Regression Intelligence

### A QA Agent That Never Forgets a Bug

An AI-powered regression intelligence system that helps QA engineers reuse historical defect knowledge to investigate recurring bugs, identify regression risks, and generate actionable insights using Hindsight memory.

<p>
  <img src="https://img.shields.io/badge/AI%20Memory-Hindsight-0D9488?style=for-the-badge" alt="Hindsight"/>
  <img src="https://img.shields.io/badge/Backend-FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white" alt="FastAPI"/>
  <img src="https://img.shields.io/badge/Frontend-React-61DAFB?style=for-the-badge&logo=react&logoColor=black" alt="React"/>
  <img src="https://img.shields.io/badge/Language-Python-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python"/>
</p>

<p>
  <a href="https://github.com/Purna3110/hfhy">Repository</a>
  &nbsp;•&nbsp;
  <a href="https://github.com/vectorize-io/hindsight">Hindsight</a>
</p>

</div>

---

## Table of Contents

- [1. Problem Statement](#1-problem-statement)
- [2. Proposed Solution](#2-proposed-solution)
- [3. Memory Performance and Accuracy](#3-memory-performance-and-accuracy)
- [4. System Architecture](#4-system-architecture)
- [5. Step-by-Step Setup Guide](#5-step-by-step-setup-guide)
- [6. Current Scope and Future Improvements](#6-current-scope-and-future-improvements)

---

## 1. Problem Statement

### The problem: QA teams keep rediscovering the same bugs.

Software applications evolve continuously. Every new feature, code change, configuration update, or deployment can introduce regressions into previously working functionality.

QA engineers often investigate these issues using bug trackers, old test reports, documentation, and previous investigation notes.

However, important knowledge is scattered across these sources. When a similar defect appears again, testers may need to repeat the same investigation because the system does not effectively connect the current issue with relevant historical defects.

### Key pain points

- **Repeated investigations:** Similar bugs can require the same debugging effort multiple times.
- **Lost institutional knowledge:** Previous root causes, fixes, and regression checks may be difficult to retrieve.
- **Limited contextual understanding:** A conventional search may return matching words without explaining why a historical defect is relevant.
- **Inconsistent regression coverage:** Important test cases may be overlooked when investigating a recurring issue.
- **No continuous learning:** A conventional LLM may not retain project-specific defect knowledge across independent sessions unless an appropriate memory system is provided.

### The real-world impact

These challenges can increase debugging effort, delay releases, and make regression testing less consistent.

<div align="center">

<img src="docs/images/integration-overview.jpg" alt="Regression Intelligence integration overview" width="90%"/>

</div>

---

## 2. Proposed Solution

### Regression Intelligence — A QA Agent That Never Forgets a Bug

Regression Intelligence is designed to turn historical defect information into reusable engineering knowledge.

Instead of treating every investigation as a new problem, the system stores defect details in Hindsight, retrieves relevant historical memories, and uses contextual reasoning to identify recurring patterns and recommend regression checks.

### How it works

**1. Retain — Learn from a defect**

When a tester submits a defect, the backend sends structured information to Hindsight.

The information can include:

- Defect ID and title
- Affected component
- Requirement ID
- Severity
- Root cause
- Fix
- Related test cases

This information becomes part of the project's defect memory.

**2. Recall — Retrieve relevant history**

When a tester investigates a new issue, the backend sends a query to Hindsight.

Hindsight retrieves relevant historical memories and supporting facts from the configured memory bank. The goal is to connect the new investigation with previously recorded defects.

**3. Reflect — Identify regression risks**

The backend asks Hindsight to analyze the historical context for recurring defect patterns and relevant regression checks.

The returned result can help a tester understand:

- Which historical defects may be relevant
- Which components or requirements may be affected
- What recurring failure patterns were recorded
- Which regression checks should be considered

**4. Display — Help the tester investigate**

The frontend presents the returned memories and regression insights so that the tester can use historical evidence during the investigation.

### Where exactly is Hindsight used?

Hindsight is the core memory layer of Regression Intelligence. The backend integrates the official `hindsight-client` SDK.

| Operation | Application endpoint | Purpose |
|---|---|---|
| Retain | `POST /api/memory/defects` | Store a new defect in memory |
| Recall | `POST /api/regression/recall` | Retrieve relevant historical defects |
| Reflect | `POST /api/regression/reflect` | Generate insights using historical defect knowledge |

Hindsight provides the memory operations; FastAPI coordinates the requests, and the React frontend presents the results.

### Why use Hindsight?

A standard LLM can reason about information supplied in a prompt, but it does not automatically have access to a project's previous investigations.

Hindsight provides a persistent memory layer that can be queried across separate investigations. Its retain, recall, and reflect operations make it possible to reuse past defect knowledge rather than relying exclusively on the current prompt.

The application uses these operations to support a memory-driven QA workflow.

---

## 3. Memory Performance and Accuracy

<div align="center">

<img src="docs/images/memory-performance.png" alt="Illustrative comparison of regression analysis approaches" width="100%"/>

</div>

### What does this comparison illustrate?

The graphic compares four approaches to regression analysis:

- Manual regression testing
- A standard LLM without project-specific memory
- A retrieval-augmented QA assistant
- Regression Intelligence with Hindsight

The intention is to illustrate how persistent, relevant defect knowledge could support a more context-aware investigation.

**Important:** The percentages shown in the graphic are illustrative values, not verified experimental results. They must not be interpreted as measured accuracy, proven improvements, or a validated benchmark.

### How should memory performance be evaluated?

A meaningful evaluation should compare the same synthetic or appropriately authorized test scenarios under controlled conditions, with and without persistent memory.

Relevant metrics include:

- **Historical defect retrieval:** Whether the expected prior defect is retrieved.
- **Recall@K:** Whether the relevant defect appears within the top K retrieved results.
- **Precision@K:** How many of the retrieved results are relevant.
- **Evidence relevance:** Whether generated insights are supported by the retrieved memories.
- **Regression recommendation quality:** Whether the suggested checks address the known failure scenario.
- **Memory contribution:** Whether access to historical memory improves results compared with the memory-disabled baseline.

The project includes a synthetic evaluation harness designed to compare memory-enabled and memory-disabled runs. Mocked tests validate application behavior, but they do not establish live Hindsight persistence or real-world accuracy.

Replace the illustrative graphic with measured results before presenting numerical performance claims.

---

## 4. System Architecture

<div align="center">

<img src="docs/images/architecture-diagram.jpg" alt="Regression Intelligence system architecture" width="100%"/>

</div>

### Architecture components

**Frontend — React, Vite and Tailwind CSS**

Provides the interface for submitting defect information and viewing regression analysis results.

**Backend — Python and FastAPI**

Exposes API endpoints, validates and processes requests, and coordinates communication between the frontend and the memory service.

**Hindsight — Persistent memory**

Stores defect information through retain, retrieves relevant historical context through recall, and supports contextual analysis through reflect.

**Groq — Optional LLM integration**

The backend also contains a separate Groq-compatible LLM test endpoint. It can be used to test LLM responses independently. The current production regression-analysis workflow uses Hindsight recall and reflect; it does not depend on the separate Groq test endpoint.

### End-to-end workflow

1. A tester submits a defect through the frontend.
2. The frontend sends a request to FastAPI.
3. FastAPI sends the defect details to Hindsight using retain.
4. During a later investigation, the backend requests relevant historical memories using recall.
5. Hindsight reflect produces contextual regression insights.
6. The backend returns the result to the frontend for display.

The quality of the result depends on the relevance of the stored memories, the retrieval results, and the quality of the analysis.

---

## 5. Step-by-Step Setup Guide

Follow these steps to run Regression Intelligence locally on Windows.

### Prerequisites

Install the following before starting:

- Python 3.10 or later
- Node.js and npm
- Git
- A Hindsight API key
- A Groq API key only if you want to test the separate Groq endpoint

### Step 1. Clone the repository

Open PowerShell and run:

```powershell
git clone https://github.com/Purna3110/hfhy.git
cd hfhy
```

### Step 2. Configure Hindsight

Create a local environment file by copying the backend template:

```powershell
cd backend
Copy-Item .env.example .env
```

Open `backend/.env` and replace the placeholder values with your credentials.

```dotenv
APP_ENV=development
API_HOST=127.0.0.1
API_PORT=8000
FRONTEND_URL=http://localhost:5173

HINDSIGHT_API_KEY=your_hindsight_api_key
HINDSIGHT_BASE_URL=https://api.hindsight.vectorize.io
HINDSIGHT_BANK_ID=hackathon-agent-memory

GROQ_API_KEY=your_groq_api_key
GROQ_BASE_URL=https://api.groq.com/openai/v1
GROQ_MODEL=llama-3.3-70b-versatile
```

Keep your actual API keys private. Never commit your `.env` file to GitHub.

The Hindsight service reads the API key, base URL, and bank ID from these environment variables. It initializes the official SDK client and uses the configured bank for retain, recall, and reflect.

If you do not need the separate Groq test endpoint, you can leave its key unconfigured. Hindsight credentials are required for the current memory service.

### Step 3. Run the backend (FastAPI)

From the `backend` directory, create and activate a Python virtual environment, install the dependencies, and start the API:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Keep this terminal running.

Verify the API using these URLs:

- API root: [http://127.0.0.1:8000/](http://127.0.0.1:8000/)
- Swagger documentation: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- Health endpoint: [http://127.0.0.1:8000/api/health](http://127.0.0.1:8000/api/health)

The API should start successfully. Requests that use Hindsight also require valid credentials and a reachable Hindsight service.

### Step 4. Run the frontend (React + Vite)

Open a **second PowerShell terminal** in the project root and run:

```powershell
cd frontend
npm install
npm run dev
```

Open the local URL printed by Vite, usually:

[http://localhost:5173](http://localhost:5173)

If the frontend needs a different backend URL, configure `VITE_API_BASE_URL` using the provided `frontend/.env.example` as a reference.

### Step 5. Add a defect and investigate a regression

<div align="center">

<img src="docs/images/setup-guide.png" alt="Step-by-step guide to use Regression Intelligence" width="100%"/>

</div>

Once both services are running:

1. Open the application in your browser.
2. Navigate to the defect submission interface.
3. Submit a defect with its title, affected component, severity, root cause, fix, and related test cases.
4. The backend sends the defect to Hindsight using retain.
5. Navigate to Regression Analysis and enter a new investigation.
6. The backend retrieves relevant historical defects using recall.
7. Hindsight reflect generates insights using the available historical context.
8. Review the returned memories and regression insights in the interface.

**Example scenario:** A tester records a payment defect caused by a gateway timeout. During a later investigation of a similar payment retry issue, the system can retrieve the historical defect and its recorded fix, if that memory is available and relevant. The tester can then use the historical evidence to decide which regression checks to perform.

This is an illustrative workflow, not a claim that the application automatically executes tests or detects every recurring defect.

---

## 6. Current Scope and Future Improvements

### Current scope

- React-based frontend with Vite.
- FastAPI backend with versioned API routing.
- Hindsight SDK integration for defect retention, retrieval, and reflection.
- A separate Groq-compatible LLM test endpoint.
- Synthetic evaluation scenarios for comparing memory-enabled and memory-disabled behavior.
- Automated backend tests for important memory-service behaviors.

### Current limitations

- Some Overview and Test Cases screens use demo data.
- The application does not automatically execute regression tests.
- The quality of analysis depends on the historical defects available in memory.
- Mocked tests do not prove live Hindsight persistence across sessions.
- The illustrative performance percentages have not been established as real benchmark results.
- Live provider connectivity and real-world accuracy must be verified separately.

### Future improvements

- Integrate with issue trackers such as Jira or GitHub Issues.
- Connect source-code changes and commits with historical defects.
- Recommend specific regression test cases from retrieved defect evidence.
- Add measured evaluation reports and retrieval-quality metrics.
- Improve traceability between requirements, defects, fixes, and test cases.
- Add more comprehensive end-to-end testing and live integration validation.

---

<div align="center">

### Built for QA teams that learn from every bug.

**Regression Intelligence — A QA Agent That Never Forgets a Bug**

Built with React, FastAPI, and Hindsight.

</div>
