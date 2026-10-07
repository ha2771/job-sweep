# job-sweep

Every two hours, a GitHub Action pulls fresh postings from public job-board APIs, screens them, and publishes one JSON file that a digest run can read in a single request. It replaces the slow browser sweeps of the company boards. LinkedIn, Indeed, Apple, and Google are not covered and stay in the browser.

**Sources:** Greenhouse, Ashby, Lever, Workday (NVIDIA, Intel, Samsung, Adobe, plus every Workday site Simplify links to), Eightfold (Microsoft, Qualcomm), Amazon, and SimplifyJobs New-Grad. Board lists come from `config.toml`, plus boards discovered automatically from the links in Simplify's listings.

**Each run does this:**
1. Keeps postings from the last 72 hours whose title passes the filters and whose location is in the US (or unclear, which is flagged).
2. Fetches the full text where the list API doesn't include it (Greenhouse, Workday).
3. Re-dates every Simplify row from the company's own board when the link points to one, which catches Simplify "refreshes" of old postings.
4. Merges same-company, same-title postings (other locations, or the same job on two sites) into one row.
5. Labels each row with a rule-based verdict and quotes the sentence that caused it.

## Setup (about 10 minutes)

1. **Create a repo** on GitHub named `job-sweep`. Public is simplest: the repo holds only public job postings and board names, never your profile or applied-to list. Actions minutes are also free and unlimited for public repos. Private works too; see "Private repo" below.
2. **Push this folder** to the repo's `main` branch:
   ```bash
   cd job-sweep
   git init -b main && git add -A && git commit -m "job-sweep"
   git remote add origin https://github.com/<you>/job-sweep.git
   git push -u origin main
   ```
3. **Run it once by hand.** In the repo, open Actions → `sweep` → "Run workflow". It takes a few minutes. After that it runs every two hours on its own.
4. **Check the result.** The run page shows a summary table. The output lands on the `sweep-output` branch, which is replaced with a single commit on every run, so the repo never grows. Read it at:
   ```
   https://raw.githubusercontent.com/<you>/job-sweep/sweep-output/candidates.json
   https://raw.githubusercontent.com/<you>/job-sweep/sweep-output/candidates.md
   ```
5. **Read the `sources` block of the first run.** Some parsers (Workday, Eightfold, Amazon) were built from the digest notes and tested only against sample data, because they could not be reached from where this was built. If a source shows `boards_ok: 0`, its errors say why. Fix it, or keep doing that source in the browser until it is fixed.

If every source fails, the run is marked failed and GitHub emails you.

### Private repo

Reading raw files from a private repo needs a token. Create a fine-grained personal access token with read-only "Contents" access to this one repo, then fetch with:

```bash
curl -sH "Authorization: Bearer $TOKEN" https://raw.githubusercontent.com/<you>/job-sweep/sweep-output/candidates.json
```

On the free plan, private repos get 2,000 Actions minutes a month, and a run every two hours uses well under that.

## Output: `candidates.json`

| Field | Meaning |
|---|---|
| `generated_at`, `generated_at_et` | When the sweep ran |
| `bootstrap_run` | `true` on the first run, when every row counts as new |
| `sources.<name>` | `boards_checked`, `boards_ok`, `postings_scanned`, `fresh_in_window`, `skipped_by_title`, `skipped_non_us`, `relevant`, `errors` |
| `jobs[]` | Sorted best first: verdict, then role track, then newest |
| `simplify_stale_after_board_check` | Simplify rows whose company-board date turned out to be old |

Each job row has these fields:

| Field | Meaning |
|---|---|
| `key` | Stable ID (`source:board:id`) for the Sent log |
| `dedupe_key` | Normalized company + title, for matching across sites |
| `url`, `company`, `title`, `locations` | The basics |
| `posted`, `age_hours`, `posted_at` / `posted_date`, `date_basis` | When it was posted and which field that date came from |
| `first_seen`, `new_this_run` | When the sweep first saw it |
| `track` | GenAI/LLM, Computer vision, Edge/inference, Signal/wireless/audio, RL/robotics, Research, Data science, ML/AI general, or Early-career (general) |
| `verdict`, `reasons`, `evidence`, `min_years`, `sponsorship_positive`, `quals_excerpt` | The triage result (below) |
| `notes`, `also_posted_as` | Caveats, and the other postings merged into this row |

**Verdicts are hints, not decisions.** Each one quotes its evidence so it can be checked in seconds.

| Verdict | Meaning |
|---|---|
| `looks_ok` | Nothing disqualifying found |
| `stretch` | Asks for 1–2 years |
| `check` | Ambiguous wording, such as a sponsorship question or export-control language |
| `no_text` | The source gives no description. Open the posting. This covers all Eightfold rows and Simplify rows that link off-board |
| `likely_drop` | PhD required, 3+ years (counting the Master's clause when there is one, so "BS+5 or MS+3" means 3), citizenship or clearance, or no sponsorship |

## Changing things

Edit `config.toml` on `main`: board lists, title regexes, Workday tenants, queries, the window. A bad token or regex fails the run with a clear message instead of silently doing nothing. `out/discovered_boards.json` also lists the most common job hosts that aren't supported yet (TikTok, SmartRecruiters, Workable, Oracle), which are good candidates for the next adapter.

## Running locally

Needs Python 3.11 or newer and no packages. On Windows, run `pip install tzdata` once.

```bash
python -m jobsweep                         # everything
python -m jobsweep --only simplify,greenhouse
pip install --require-hashes -r requirements-dev.txt && python -m pytest -q
```

## Design notes

- **No runtime dependencies.** The sweep uses the standard library only: HTTPS-only requests, per-host concurrency caps, retries with backoff on 429/5xx, and a 64 MB response cap.
- **External data is untrusted.** Board names, from config or from Simplify links, are checked against a strict pattern before they go into API URLs, and every JSON field is type-checked before use. One failing board is recorded and the run continues.
- **Pinned and audited.** Actions are pinned to commit SHAs, test dependencies are pinned by hash, and Dependabot proposes monthly updates.
