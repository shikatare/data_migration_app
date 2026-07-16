## Migration Agent — Baseline Checkpoints

Purpose: a reproducible set of checkpoints to verify the MySQL → Snowflake
Migration Agent is working correctly. Each checkpoint has exact commands,
what to expect, and what a pass/fail means. Run them in order — later
checkpoints assume earlier ones pass.

**Estimated time:** ~20–30 minutes for all checkpoints.

---

## 0. Prerequisites

- Python 3.12+ and Node.js installed
- A MySQL server reachable (local or remote) — for Checkpoint 4+
- A Snowflake account with `CREATE TABLE` privilege on a target schema — for Checkpoint 5+
- A Groq API key (free tier is fine) — for Checkpoint 3+

If you only want to verify the **pipeline logic** without any external
accounts, Checkpoints 1–2 are sufficient and require nothing but this
codebase.

---

## 1. Environment setup

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

**Expected:** `pip install` completes with no errors. You should see
packages including `fastapi`, `langgraph`, `langchain-groq`, `sqlglot`,
`mysql-connector-python`, `snowflake-connector-python`, `reportlab`.

**If this fails:** stop here — nothing downstream will work. Most common
cause is a Python version mismatch; confirm `python3 --version` is 3.10+.

---

## 2. Checkpoint 1 — Backend starts cleanly (offline, no external accounts)

Edit `backend/.env` and set:
```
LLM_PROVIDER=mock
MYSQL_MODE=mock
SNOWFLAKE_MODE=mock
```

Start the server:
```bash
uvicorn app.main:app --reload --port 8000
```

**Expected terminal output**, ending with no error:
```
INFO:     Application startup complete.
```

In a second terminal:
```bash
curl http://localhost:8000/api/health
```
**Expected:** `{"ok":true}`

```bash
curl http://localhost:8000/api/pipeline/config
```
**Expected:** `{"mysqlMode":"mock","snowflakeMode":"mock","llmProvider":"mock",...}`

**Pass criteria:** both curl calls return the expected JSON with no
connection errors.
**What this proves:** the FastAPI app, all four agents, and all adapters
import and initialize correctly with zero external dependencies.

---

## 3. Checkpoint 2 — Full pipeline runs end-to-end offline

With the server still running in mock/mock/mock mode from Checkpoint 1:

```bash
curl -X POST http://localhost:8000/api/pipeline/agentic-runs \
  -H "Content-Type: application/json" \
  -d '{"schemaName":"CUSTOMER_ORDERS","approved":true}'
```
**Expected:** `{"runId":"run_xxxxxxxxxx","room":"run:run_xxxxxxxxxx"}`

Wait 3 seconds, then:
```bash
curl http://localhost:8000/api/pipeline/runs
```
**Expected:** a JSON array where the newest entry has:
- `"overallStatus": "success"`
- `"confidence"` populated (a number between 0 and 1)
- `"extract"`, `"convert"`, `"validateDeploy"` all populated with data

**Pass criteria:** the run reaches `success` status with all four stage
outcomes present.
**What this proves:** the four-agent pipeline (Extract → Convert →
Validate → Deploy → Log & Notify) runs correctly end to end using the
built-in sample schema and deterministic offline converter — no LLM, no
real database, no cloud account required. This is the fastest way to
confirm the core logic works.

---

## 4. Checkpoint 3 — Real LLM (Groq) reasoning + self-correction

Edit `backend/.env`:
```
LLM_PROVIDER=groq
GROQ_API_KEY=<a real Groq API key>
FORCE_VALIDATION_FAIL_ONCE=true
```
Restart the server (`Ctrl+C`, then re-run the `uvicorn` command).

Run a migration the same way as Checkpoint 2 (via `curl` or the frontend —
see Checkpoint 6 for frontend setup).

**Expected in the Run log:** Convert runs, Validate fails once
(intentionally, for this test), Convert runs *again* automatically with
the specific error as feedback, Validate passes on the second attempt.

**Pass criteria:** the run still reaches `success` despite the forced
first failure — no human intervention, no crash.
**What this proves:** this is the actual "agentic" behavior — a real LLM
(not a script) deciding to retry with corrective feedback when validation
fails. Set `FORCE_VALIDATION_FAIL_ONCE=` (blank) afterward for normal use.

---

## 5. Checkpoint 4 — Real MySQL source

Edit `backend/.env`:
```
MYSQL_MODE=real
MYSQL_HOST=<your host>
MYSQL_PORT=3306
MYSQL_USER=<your user>
MYSQL_PASSWORD=<your password>
MYSQL_DATABASE=<a database that exists on that server>
```
Restart the server.

```bash
curl http://localhost:8000/api/pipeline/schemas
```
**Expected:** a list of your real MySQL database names (not just the two
sample schema names).

Run a migration on one of your real databases.

**Pass criteria:** the `extract` stage of the run shows the actual table
names and column types from your real database (not `CUSTOMERS`/`ORDERS`
unless that's genuinely what's there).
**What this proves:** the Extract agent connects to a live MySQL server
via `INFORMATION_SCHEMA` and works on arbitrary real schemas, not just
the two bundled samples.

---

## 6. Checkpoint 5 — Real Snowflake deployment

Edit `backend/.env`:
```
SNOWFLAKE_MODE=real
SNOWFLAKE_ACCOUNT=<your account identifier>
SNOWFLAKE_USER=<your user>
SNOWFLAKE_PASSWORD=<your password>
SNOWFLAKE_WAREHOUSE=<your warehouse>
SNOWFLAKE_DATABASE=<your database>
SNOWFLAKE_SCHEMA=<your schema>
```
Restart the server. Ensure the target schema does **not** already contain
tables with the same names as what you're migrating (drop them first if
re-running a prior test).

Run a migration.

**Pass criteria:** the run reaches `success`, and in Snowflake itself:
```sql
SHOW TABLES;
```
shows the newly created tables.
**What this proves:** the full pipeline works against real production
systems on both ends — genuine schema migration, not a simulation.

---

## 7. Checkpoint 6 — Frontend console + downloadable report

```bash
cd frontend
npm install
npm run dev
```
Open `http://localhost:5173` in a browser.

**Expected:** the schema dropdown populates automatically. Selecting a
schema and clicking **Run migration** shows all four pipeline stages
updating live (Extract → Convert → Validate → Deploy), and on success the
Results panel shows a confidence percentage, a recommendation, and a list
of any columns flagged for human review.

Click **Download review report**.

**Pass criteria:** a PDF downloads and opens, showing the run ID, overall
confidence, the three validation checks with pass/fail status, a
per-table confidence breakdown, and a reviewer sign-off section.
**What this proves:** the full user-facing product works — live progress
streaming (Socket.IO), the confidence scoring UI, and the report
generation feature all function together.


---

## 7. Checkpoint 7 — Review-before-deploy mode

With the server and frontend running (same setup as Checkpoint 6):

1. In the console, check **"Review DDL before deploy"** before selecting a
   schema.
2. Select a schema and click **Run migration**.

**Expected:** Extract and Convert run exactly as before, but instead of
continuing automatically, the screen replaces the Run Log / Results panels
with a **DDL review editor** — one editable text box per table, showing the
exact converted Snowflake DDL.

3. Without changing anything, click **Approve & Continue**.

**Expected:** Validate and Deploy proceed normally, reaching `success`, with
the confidence panel and report download appearing as usual.

**Pass criteria:** the pipeline visibly pauses after Convert and only
proceeds once you click Approve & Continue — confirming a human checkpoint
genuinely sits between conversion and deployment, not just cosmetically.

**What this proves:** a reviewer can inspect (and, if needed, edit) the
AI's proposed conversion before anything touches the target system — this
closes the "how does someone act on a flagged item" gap from Section 12 of
the project report; it is no longer a limitation.

### 7.1 Sub-check — editing is respected

1. Run again with review mode checked.
2. When the editor appears, deliberately change one table's DDL (e.g. add a
   `CHECK` constraint, or fix a flagged column type).
3. Click **Approve & Continue**.

**Expected:** the deployed table in Snowflake reflects your edited DDL, not
the original AI-generated version — confirm via `DESCRIBE TABLE` /
`GET_DDL()` in Snowflake.

### 7.2 Sub-check — a bad edit is caught, not silently deployed

1. Run again with review mode checked.
2. When the editor appears, delete a column from one table's DDL text.
3. Click **Approve & Continue**.

**Expected:** validation fails (structural diff catches the missing
column), and the editor **reappears** with the specific error shown,
rather than the pipeline deploying the broken schema or crashing.

**Pass criteria:** the run does *not* appear in the completed Audit trail
until a valid version is approved — confirming the system never silently
deploys something it flagged as broken.

## 8. Checkpoint 8 — Failure handling (governance / safety check)

Run the same schema a second time without dropping its Snowflake tables
first.

**Expected:** Extract, Convert, and Validate still succeed and the
confidence data still populates in the Results panel; only Deploy fails,
with a clear error message (`Object 'X' already exists`) rather than a
silent crash or corrupted state.

**Pass criteria:** the run is marked `deploy_failed` (not left in limbo),
appears correctly in the Audit trail, and the report/confidence data is
still available for that run.
**What this proves:** the system fails gracefully and never silently
loses data — every run, successful or not, is fully recorded.

---

## Summary checklist

| # | Checkpoint | Requires | Pass signal |
|---|---|---|---|
| 1 | Backend starts | Nothing external | `{"ok":true}` from `/api/health` |
| 2 | Full offline pipeline | Nothing external | Run reaches `success` in mock mode |
| 3 | Real LLM + self-correction | Groq API key | Run recovers from a forced validation failure |
| 4 | Real MySQL source | MySQL server | Schema list shows real databases |
| 5 | Real Snowflake deploy | Snowflake account | Tables appear in `SHOW TABLES;` |
| 6 | Frontend + report | Node.js | PDF downloads with confidence data |
| 7 | Graceful failure | Same as 5 | Failed deploy still logs full data |

Checkpoints 1–2 require no credentials at all and are the fastest way to
verify the core pipeline logic is sound. Checkpoints 3–7 progressively
add real external systems to prove the full production path works.
