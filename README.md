# Phở around 🍜

**Tell it where you are in Sài Gòn, how much time you have, and your budget — get back an
optimized outing: which spots, in what order, with honest travel times.**

### 👉 Try it: **[pho-around.vercel.app](https://pho-around.vercel.app)** — no account, no signup

> **First load may take 30–60 seconds.** The backend sleeps on its free tier and has to wake up;
> everything after that is fast. The loading panel will tell you it's thinking.

Most "where to eat" apps are searchable lists. Phở around treats an afternoon out as an
**optimization problem**: it picks a subset of ~100 curated places and orders them into the
best route that fits your time and money — using real Operations Research, not a sorted list.

![Phở around: a start point in District 1 with time and money budgets on the left, and the
optimized three-stop route drawn on the map on the right](docs/screenshot.png)

## How it works

1. Tap the map (or use your location) to set a start point, pick a time budget and a spending
   budget.
2. The backend solves an **orienteering problem** — a prize-collecting traveling-salesman
   variant — as a mixed-integer linear program (PuLP + CBC): maximize the total appeal of
   visited places, subject to your time budget (dwell + travel + a realism buffer per stop)
   and your money budget, with MTZ constraints keeping the route a single connected path.
3. The route renders as numbered pins and a path on a custom-styled Google Map, with per-leg
   ride times and a running total — every stop deep-links into Google Maps for photos, hours
   and reviews.

Some details the optimizer gets right that a list never could:

- **Travel time is real.** Place-to-place motorbike times come from a precomputed Routes API
  matrix (`TWO_WHEELER` — this is Sài Gòn). The leg from *your* start point is estimated by a
  distance formula calibrated against all 1,988 real legs in that matrix: 12.6 km/h, the city's
  measured median riding speed, with a median error of 1.7 minutes. Live traffic-aware start
  legs are a one-flag upgrade (`USE_LIVE_START_LEGS`), left off so the public demo costs
  nothing to run.
- **Routes don't zigzag.** Travel enters the objective as a carefully-sized tiebreaker, so
  among equally-appealing plans the solver always returns the shortest ordering — without
  ever sacrificing a better place to save a minute of riding.
- **It doesn't overpromise.** Every stop is charged a parking/queueing buffer, and the time
  budget is hard — the plan you get is one you can actually live.
- **It scales politely.** Each request pre-filters the dataset to 25 candidates — the 18
  nearest to *your* start, plus the 7 best anywhere in the city — so a far-away gem always
  keeps its seat at the table. That number is measured, not guessed: on the deployment's
  modest CPU a 40-place pool sometimes failed to find *any* plan in time, while 25 delivers
  98.7% of its own best objective under pressure.

## The data

~100 real Sài Gòn places — phở and bún bò to specialty coffee, photobooths, museums and
landmarks — hand-curated (dwell times, real VND prices, categories are human judgement),
with facts (coordinates, ratings, place ids) resolved through the Geocoding and Places APIs
by a small family of dry-run-first import scripts in [`backend/scripts/`](backend/scripts/).

## Stack

| Layer | Choice |
|---|---|
| Frontend | React + Vite, plain JavaScript, hand-written CSS design system |
| Map | Google Maps JavaScript API (custom cloud style, advanced markers) |
| Backend | FastAPI (Python) |
| Optimizer | PuLP + CBC (mixed-integer linear programming) |
| Travel times | Google Routes API (`computeRouteMatrix`, two-wheeler mode) |
| Data | Curated JSON seed + precomputed sparse travel-time matrix |
| Hosting | Vercel (static frontend) + Render (uvicorn + solver) |

The split is deliberate: the frontend is static files, which a CDN serves for free from
everywhere, while a request that spends seconds inside a native MILP solver is a poor fit for
serverless duration caps and a fine fit for an ordinary long-lived process.

## Running locally

Two dev servers, two terminals. You'll need a Google Cloud project with the Maps JavaScript,
Geocoding, Routes and Places APIs enabled, and two API keys (see the `.env.example` files —
a browser key locked by referrer + API restrictions, and a server key kept server-side).

```bash
# backend — http://127.0.0.1:8000
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn api:app --reload

# frontend — http://localhost:5173
cd frontend
npm install
npm run dev
```

Tests: `python -m pytest` from `backend/` — 67 covering the engine, the HTTP layer,
travel-time lookup, the incremental matrix builder, and the solver's behaviour pinned by
hand-checkable instances.

## Status

**Live since August 2026.** The v1 core loop is complete and deployed: optimized routes over
real data on a designed UI, reachable from any phone.

Deployment taught more than local development could. A solver timeout was silently discarding a
perfectly good plan, because CBC reports "Not Solved" when the clock stops the search even
though the route it's holding is feasible. A candidate pool that was comfortable on a laptop
found nothing at all on a shared tenth of a CPU. And a travel-time matrix rebuilt three times
during development arrived as a $106 bill — which is why the running app now makes zero API
calls per click, and why every import script asks before it spends.

Next: an LLM planning layer that turns natural language into typed constraints for the solver —
the model proposes, the solver still disposes — then saved itineraries and the accounts they
require.

---

*A full-stack learning project, built end-to-end — data modeling, MILP optimization, API
design, React, and a lot of respect for Sài Gòn traffic.*
