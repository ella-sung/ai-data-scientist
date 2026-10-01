# AI data scientist

An autonomous analysis loop. Point it at a CSV and a business question; it
profiles the data, checks it for leakage, proposes a few approaches, writes and
runs its own Python, gets reviewed by a second model, and produces two
deliverables: a Markdown report and a self-contained HTML dashboard.

Same architecture as `JinyanSu1/Agentic-AI-Scientist` — propose, pilot, execute,
judge, render, remember — with the research-paper machinery replaced by a
report and a dashboard.

```
profile → validity checks → propose plans → pick one
        → [ analyse → judge ] until "keep" or the round cap
        → report.md + dashboard.html
```

---

## Step 1 — set up

```bash
cd ai-data-scientist
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
python -m pip install -r requirements.txt
```

## Step 2 — add your API key

```bash
cp .env.example .env
```

Edit `.env` and paste your key from console.anthropic.com. `.env` is already in
`.gitignore`, so it will never be committed.

## Step 3 — generate the data

```bash
python data/generate_data.py
```

Writes `data/subscriptions.csv`: 9,070 rows of synthetic SaaS subscription
records with a `churned` label. It is deliberately imperfect — 11% missing NPS,
70 duplicated accounts, inconsistent region casing, and one planted leakage
column (`exit_survey_sent`, which is only ever set for customers who already
cancelled). The pipeline is supposed to catch that column. If it ever silently
uses it, something is broken.

## Step 4 — run the free dry run first

```bash
python demo_no_api.py
```

No API calls, no cost. It exercises the profiler, the validity checks, the code
sandbox and both renderers using a fixed analysis. Open
`workspace/demo/dashboard.html` in a browser. If that looks right, the whole
plumbing works and only the model calls remain untested.

## Step 5 — run the real thing

```bash
python run.py --csv data/subscriptions.csv --target churned \
  --question "Which customers churn, why, and what should we do about it?"
```

Expect roughly 3–8 minutes and a low single-digit dollar cost per run on Sonnet.
Output lands in `workspace/run_<timestamp>/` and is copied to
`workspace/latest/`:

| File | What it is |
| --- | --- |
| `dashboard.html` | The interactive dashboard. One self-contained file — CSS, JS and data inlined — so it works offline and can be emailed as a single attachment. |
| `report.md` | The written report. |
| `findings.json` | The structured findings the narrative sections render from. |
| `cube.json` / `cube_rows.csv` | The row-level data the dashboard filters over in the browser. |
| `transcript.json` | Every block of code the agent ran and what it printed. Read this when you don't believe a number. |
| `checks.json` | Leakage and baseline results. |
| `plan.json` | The plan that was chosen and why. |
| `figures/` | The PNGs. |

Useful flags:

| Flag | Default | Meaning |
| --- | --- | --- |
| `--max-rounds` | 3 | analyse/judge cycles before giving up |
| `--max-turns` | 25 | tool calls allowed inside one analysis round |
| `--num-plans` | 3 | candidate approaches proposed |
| `--backend` | subprocess | `docker` for real isolation |
| `--outdir` | timestamped | where to write |

## Step 6 — turn on real isolation

`--backend subprocess` runs model-written code as your user, on your machine.
That is fine while you are watching it. Before you leave a run unattended:

```bash
docker build -t ds-agent:latest .
python run.py --backend docker ...
```

The container gets the data read-only, no network, capped memory and CPU, and is
destroyed after each step.

---

## How it fits together

| File | Role |
| --- | --- |
| `dsagent/profiler.py` | Deterministic data card. Runs before the model sees anything, so it reasons about real columns instead of guessing. |
| `dsagent/checks.py` | Leakage detection, duplicate counting, trivial baselines. Plain Python. The model may interpret these; it may never certify itself. |
| `dsagent/sandbox.py` | Runs model-written code with a timeout, in a scratch directory, optionally in Docker. |
| `dsagent/llm.py` | The API client and `agent_loop` — the model asks to run code, we run it, we hand back the output, repeat. That function is the entire idea. |
| `dsagent/stages.py` | The three prompts: plan, analyse, judge. |
| `dsagent/outputs.py` | Deterministic rendering: the Markdown report and the dashboard shell. |
| `dsagent/dashboard.css` | Dashboard styling. Edit this to restyle without touching Python. |
| `dsagent/dashboard.js` | SVG chart kit and filter/slider logic for the account view. |
| `dsagent/weekly.py` | Weekly-report cube builder and renderer. |
| `dsagent/weekly.css` / `weekly.js` | Styling and logic for the weekly report. |
| `data/generate_gofundme_data.py` | Synthetic two-sided marketplace + subscription data. |
| `run.py` | Wires it together. |

Three design decisions worth understanding, because they are what separate this
from a chatbot that prints plausible numbers:

**The judge is a separate call that never sees the analyst's reasoning.** It
gets the code, the output and the findings, and must cite evidence. An agent
asked to review its own work approves it essentially always.

**Leakage checks are code, not prompts.** `exit_survey_sent` gives an AUC of
0.96 and means nothing. A model asked "is there leakage?" will often say no. A
rank test finds it every time, and the result is injected into the prompt as a
fact the analyst must act on.

**The model produces structured findings and a data cube; Python renders them.**
If the model wrote HTML you would get a different layout each run and
occasionally a broken one. The agent exports `cube_rows.csv` — one row per
account with segment, revenue, recency, outcome and predicted risk — and the
dashboard recomputes every number from it in the browser. Nothing on the page is
a pre-rendered picture.

## Two dashboard templates

The loop is the same either way; only the renderer differs. Pick the one whose
shape matches your question.

| Template | Question it answers | Data shape |
| --- | --- | --- |
| `outputs.py` + `dashboard.js` | Who is at risk right now? | one row per account |
| `weekly.py` + `weekly.js` | What changed this week, and where? | week × segment × channel |

### Weekly operating report (`demo_gofundme.py`)

```bash
python data/generate_gofundme_data.py
python demo_gofundme.py
# opens workspace/gofundme/weekly_report.html
```

Synthetic data modelled on GoFundMe's publicly described business structure. It
is deliberately two-sided, because a marketplace and a subscription business do
not share a definition of churn:

- **Marketplace.** Personal campaigns, revenue from voluntary donor tips plus
  processing margin. "Churn" means an organizer never runs a second campaign.
  Acquisition is 58% organic and viral at a $1.79 CPA, because campaigns market
  themselves when organizers share them.
- **Subscriptions.** Nonprofit accounts, where MRR churn, CAC payback and LTV
  mean what they normally mean.

Averaging the two produces a platform churn number that means nothing. The
report keeps them in separate bands.

Interactive parts: a **week stepper** with week-over-week and trailing-four-week
deltas on every KPI; a **trend chart** with five selectable metrics where
clicking any point jumps the whole report to that week; **CAC by channel** as
spend bars against a cost-per-organizer line; **cohort retention curves** by
acquisition channel; a **category table** for the selected week; and a
**week-over-week movers** list that colours a move by whether it is in the right
direction, so rising CAC reads as red even though the arrow points up.

Two findings are planted in the data for the pipeline to catch. Paid social is
ramped from week 18, its CPA rising 24% while every other channel holds flat,
and the same channel retains worst on the subscription side at 41% against 57–62%
elsewhere. Separately, memorial campaigns repeat at 6% against 62% for nonprofit
campaigns — high churn that is structural rather than a failure, and the analysis
is expected to say so rather than recommend fixing it.

## The account-risk dashboard

Open `workspace/latest/dashboard.html`. It is one file, works offline, and
fetches nothing.

- **Segment filters** across plan, region and contract type. Every KPI, chart
  and table below recomputes on click.
- **Outreach simulator.** Two sliders set the thresholds a customer-success team
  would actually operate on: minimum days of inactivity, and minimum model risk
  score. It reports the size of the resulting list, the share of churners it
  catches, the hit rate, and the MRR it covers. This is the part that turns an
  analysis into a decision — at 14 days and 30% risk the list is 508 accounts
  with an 81% hit rate; tighten to 30 days and it drops to 188 accounts at 83%.
- **Charts** for churn by plan and churn by dormancy, both filter-aware, plus a
  model-level driver chart from permutation importance.
- **Account table** showing the highest-risk accounts in the current selection.

Charts are hand-rolled SVG in `dashboard.js` — roughly 200 lines, no Chart.js,
no D3, nothing loaded from a CDN. That keeps the file portable and means you can
read and change the whole rendering path.

### Adapting it to your own data

The dashboard reads a fixed eight-column contract: `id, plan, region, contract,
mrr, dorm, churned, risk`. The agent is told to map your columns onto those
names. For a non-churn dataset, treat them as: identifier, three segment
dimensions, a value measure, a recency measure, a binary outcome, and a model
score. Change the labels in `dashboard.js` and the copy in `outputs.py`.

## Extending it

The obvious next additions, in the order I would do them:

1. **Memory.** Append one line per attempt to `research_wiki.jsonl` — what was
   tried, the verdict, one sentence on why — and feed it into `propose_plans`.
   Stops the loop rediscovering the same dead ends.
2. **Pilots.** Right now one plan is chosen by argument. Run each plan for 8
   turns on a 10% sample and pick the winner on measured signal instead.
3. **Time-aware validation.** `signup_date` is present and unused. A temporal
   split turns this from association into forecasting.
4. **Cost caps.** Track token usage per stage and abort above a threshold.
5. **Your own data.** Nothing here is churn-specific except the dashboard header
   and the default question. Swap the CSV and the `--target`.
