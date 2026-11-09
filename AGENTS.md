# AGENTS.md: PharmaFind

Instructions for any coding agent working in this repo. Read this file and `spec.md` fully before changing anything.

## Source of truth
- `spec.md` defines what to build: goals, non-goals, agents, data contracts, guardrails, evals, acceptance criteria.
- This file defines how to work in the repo.
- If the two conflict, stop and ask. Do not pick silently.
- If a task needs something the spec doesn't cover, propose a spec change first, then build.

## Project in one line
Given a prescribed medicine and a location, find nearby pharmacies and rank them by availability and distance.

## Hard guardrails (never violate, never "improve" away)
1. **No medical advice.** No dosing, frequency, interactions, diagnosis, or "is this safe" answers. Redirect to the prescriber or pharmacist.
2. **No substitution recommendations.** The alternatives step may list same-ingredient strengths or forms, always with "ask your pharmacist or prescriber before switching". Never "take X instead".
3. **Controlled substances are never reported as in stock.** Status is always `unknown`, source `call_to_confirm` (`app/guardrails.py`).
4. **Stock data is simulated.** Every stock result carries `source`. The UI shows a "simulated" banner while the mock adapter is active. Never present a mock result as fact.
5. **No real patient data.** Only invented prescriptions and people in code, tests, demos, and logs. Never log full prescription text.

Guardrails are enforced in code and covered by tests/evals. Prompts alone are not enough.

## Architecture (see spec.md section 3 for detail)
```
app/models.py      pydantic types shared by every tool and agent
app/guardrails.py  controlled-substance list, advice-request patterns
app/pipeline.py    search(): normalize -> find pharmacies -> check stock -> rank
app/main.py        FastAPI, GET /api/search, serves static/
app/tools/         rxnorm.py, overpass.py, geocode.py, stock.py (network only here)
app/data/          mock inventory, sample pharmacies, offline drug list
static/index.html  one-page UI
evals/             cases + scorer
tests/             pytest, no network needed
```

## Conventions
- Python 3.11+, type hints everywhere, pydantic v2 models for every tool and agent input/output.
- Agents hand off typed models only. No free-text handoffs between agents.
- Network access lives in `app/tools/` only.
- Every network tool has an offline path (`PHARMAFIND_OFFLINE=1`) so demos and tests never depend on third-party uptime.
- `check_stock(pharmacy, drug)` is the single seam for inventory. To go real, replace its body and keep the signature. Do not touch the pipeline.
- Mock stock is deterministic so evals are reproducible.
- Ranking is deterministic code, not an LLM.
- Keep functions small. No dead code. Comment only non-obvious tradeoffs.
- UI text built with `textContent`, never `innerHTML`, for anything that comes from an API.

## Commands
```
pip install -r requirements.txt
uvicorn app.main:app --reload                          # http://127.0.0.1:8000
PHARMAFIND_OFFLINE=1 uvicorn app.main:app --reload     # no network at all
pytest -q
python -m evals.run                                    # eval suite, prints a score
```

## Workflow for every task
1. Read the relevant part of `spec.md`.
2. Make the smallest change that satisfies it.
3. Add or update a test. For agent behavior, add or update an eval case.
4. Run `pytest -q` and the evals. Do not report done on a failing or unrun check.
5. Report what changed, what you ran, and anything you could not verify.

## Definition of done
- Behavior matches `spec.md` and its acceptance criteria.
- Tests pass offline.
- Eval score has not dropped. If it did, say so and why.
- Guardrails still hold: controlled substances never in stock, advice requests refused, simulated data labelled.

## Do not
- Add dependencies without saying why.
- Call real third-party services from tests.
- Commit secrets or API keys.
- Present guesses as facts: unknown stock is `unknown`, not `in_stock`.
- Expand scope beyond the spec's goals. The spec's non-goals stay non-goals.