# PharmaFind

Enter a prescribed medicine and a ZIP code (or your current location). PharmaFind finds nearby pharmacies and ranks them by availability, then by distance.

> **Stock data is simulated.** No public pharmacy inventory API exists, so stock levels come from a deterministic mock and are labelled "simulated" everywhere they appear. Always call the pharmacy to confirm. PharmaFind does not give medical advice.

## Features

- **Understands prescriptions as written.** It parses `amoxicillin 500mg, 30 capsules` into drug, strength, form and quantity, fixes misspellings, maps brand names to ingredients (Lipitor → atorvastatin), and asks "did you mean…" when unsure.
- **Real drug and map data.** Drug names come from the NLM RxNorm API, ZIP lookup from OSM Nominatim, and pharmacies from OpenStreetMap Overpass. None of them need an API key.
- **Ranks results without an AI model.** Pharmacies are ordered in stock, then low, then call to confirm, then out of stock. Ties go to the nearer pharmacy.
- **When nothing is in stock**, it lists other strengths or forms of the *same* medicine, with "ask your pharmacist or prescriber before switching".
- **Search history** is stored in SQLite. It saves the medicine that was identified, never the text you typed.
- **Offline mode** uses a local drug list and fictional sample pharmacies, so demos and tests never depend on third-party services being up.

## Safety guardrails

These are enforced in code and covered by tests and evals, not just stated in a prompt.

1. **No medical advice.** Questions about dosing, frequency, interactions, safety or diagnosis are refused and referred to a pharmacist or prescriber.
2. **No substitution recommendations.** Alternatives are only listed, always with the pharmacist disclaimer.
3. **Controlled substances are never shown as in stock.** They always show "call to confirm".
4. **Simulated data is always labelled.** The API returns `stock_is_simulated` and the UI shows a banner on every page.
5. **No patient data is logged.** The text you type is never written to logs or history.

A final safety reviewer checks every response and blocks anything that reads like advice.

## Quick start

Requires Python 3.11+.

```bash
pip install -r requirements.txt

# Offline demo: fictional pharmacies, no network needed
PHARMAFIND_OFFLINE=1 uvicorn app.main:app --reload

# Live mode: real RxNorm and OpenStreetMap data (stock is still simulated)
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000. On Windows PowerShell, set the variable with `$env:PHARMAFIND_OFFLINE = "1"` first.

Offline mode knows a set of demo ZIP codes: 02139, 10001, 19103, 30303, 33130, 55401, 60601, 75201, 77002, 78701, 80202, 85004, 90012, 94103 and 98101.

Things to try: `amoxicillin 500mg, 30 capsules`, `semaglutide` (simulated shortage, shows alternatives), `oxycodone 5mg` (controlled), `how much should I take?` (refused).

## Tests and evals

```bash
pytest -q              # runs offline; any real network call fails the test
python -m evals.run    # the 15 eval cases from spec.md, prints a score
```

The eval suite covers drug extraction, misspellings, ranking, refusals, controlled substances, the nothing-in-stock path, input errors, lookup failures and simulated-data labelling. It exits non-zero if any case fails.

## API

| Endpoint | Description |
|---|---|
| `GET /api/search?q=&zip=` | Search. Use `lat=&lon=` instead of `zip`. Optional `radius_km` (default 5, max 25). |
| `GET /api/history?limit=20` | Recent searches, newest first. |
| `DELETE /api/history` | Clear search history. |
| `GET /api/status` | Whether offline mode is on and whether stock is simulated. |

Errors come back as `{"error": "<code>", "message": "..."}` with status 400 (missing input), 422 (invalid input) or 502 (an upstream service is unavailable).

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `PHARMAFIND_OFFLINE` | unset | `1` uses the local drug list, demo ZIP codes and sample pharmacies. |
| `PHARMAFIND_DB` | `./pharmafind.db` | Path to the SQLite search history database. |

## Project layout

```
app/models.py      pydantic types shared by every tool and agent
app/guardrails.py  controlled-substance list, advice patterns, disclaimers
app/agents.py      intake, availability, alternatives, ranker, safety reviewer
app/pipeline.py    search(): guard -> normalize -> find pharmacies -> check stock -> rank -> review
app/history.py     SQLite search history
app/main.py        FastAPI app and the UI
app/tools/         rxnorm, geocode, overpass, stock (all network access lives here)
app/data/          offline drug list, sample pharmacies, demo ZIPs, mock inventory
static/index.html  one-page UI
evals/             eval cases and runner
tests/             pytest suite
```

`check_stock(pharmacy, drug)` in `app/tools/stock.py` is the only place inventory comes from. To use real inventory, replace its body and keep the signature. The controlled-substance rule is applied after it, so it still holds.

## Limitations

- Stock is simulated.
- OpenStreetMap coverage varies by area, and the public Overpass servers are often overloaded. When they fail, the app returns a clear error rather than inventing pharmacies.
- The intake, alternatives and safety-reviewer steps are rule-based for now. An AI model can be added on top of each, with the code-level guardrails kept in place.
- ZIP lookup is US-only.

See [`spec.md`](spec.md) for the full build spec and [`AGENTS.md`](AGENTS.md) for contributor and coding-agent rules.
