# Agent evals

A test bench for this repo's coding agent. It measures how well a given model uses the agent's tools: reading
files, editing code, running commands, and refusing requests it shouldn't fulfil.

Each **task** is a small, realistic job (for example "fix the bug so the tests pass"). The harness runs the
real chat engine on it in a throwaway project folder, scores the outcome automatically, and repeats it because
models are non-deterministic. You get pass rates, speed and cost per model, so you can:

- **pick a model**: which one is reliable enough, and what does it cost?
- **catch regressions**: did my change to the agent's prompts or tools make it better or worse?

## Quick start

Run everything from the repository root. One-time setup:

```bash
pip install -r requirements-dev.txt     # the app's dependencies plus pytest
```

For a hosted model, put its API key in `.env` (copy `.env.example` to `.env` if you don't have one yet). The
commands below read it automatically:

```
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
GOOGLE_AI_STUDIO_API_KEY=...
```

For **LM Studio** (or Unsloth), load a model and start its local server instead; no key is needed.

Then:

```bash
# 1. Check the harness itself. No model, no key, free, takes seconds.
python -m evals selfcheck

# 2. First real run: one model, two tasks, one repeat (cheap).
python -m evals run --provider openai --model gpt-5.4-mini --tasks read_and_answer,count_files --repeats 1

# 3. Every task on one model (3 repeats each by default).
python -m evals run --provider anthropic --model claude-haiku-5-5

# 4. Several models side by side. Run with no options and a menu walks you through it.
python -m evals matrix

# 5. Open the results in your browser.
python -m evals dashboard --open
```

`run` and `matrix` build the report themselves when they finish and print where it is. Step 5 just reopens it
later.

### How big is a run?

Runs = models x tasks x repeats. The defaults are 11 tasks x 3 repeats = **33 runs per model**. In our runs
that cost from a few cents to under a dollar per model, depending on the model (see [Cost](#what-it-costs)).
To check before spending anything:

```bash
python -m evals matrix --providers openai --dry-run     # prints the plan, runs nothing
```

Start small with `--tasks` and `--repeats 1`, then widen.

## More run commands

```bash
# One model on each provider
python -m evals run --provider lm_studio --repeats 3                  # whichever model is loaded
python -m evals run --provider openai    --model gpt-5.6-terra
python -m evals run --provider anthropic --model claude-sonnet-5-5
python -m evals run --provider google    --model gemini-3.8-flash
python -m evals run --provider unsloth

# Many models at once
python -m evals matrix --providers openai,anthropic,google            # each provider's default models
python -m evals matrix --models openai:gpt-5.6-terra,anthropic:claude-sonnet-5-5 --repeats 5
python -m evals matrix --providers openai --tasks fix_failing_test,refactor_extract_duplicate

# See each run's task, tool calls and answer as it finishes
python -m evals run --provider openai --model gpt-5.4-mini --verbose

# Grade the free-text task with an LLM judge (use a different model than the one being tested)
python -m evals run --provider lm_studio --judge --judge-provider openai --judge-model gpt-5.4-mini
```

`matrix` takes `provider:model` pairs (`--models`) and/or whole providers (`--providers`, which use the
defaults in `evals/matrix_defaults.json`). A bare `lm_studio` means whichever model is loaded. With neither
option it shows a menu: which providers are ready (key found or server reachable), which models, how many
repeats, which tasks, then asks to confirm. Press Enter to accept each default.

## Reading the results

Every `run` or `matrix` invocation gets its own timestamped folder, and nothing is ever overwritten:

```
evals/results/
  index.html                       every run, newest first. Click a row to open it.
  runs/20261009-150237/            the run's start time: YYYYMMDD-HHMMSS
    dashboard.html                 this run's full report (start here)
    comparison.md                  the same numbers as a plain table
    run.json                       what was run, on which code, and how it ended
    openai__gpt-5.6-terra.json     scored results, one file per model
    traces/<provider>__<model>/    every prompt, tool call and answer, plus run_log.txt
```

The report is a single self-contained HTML file (no server, no network), so you can email it or open it
offline. From top to bottom it has:

- **Headline tiles and "What the data says"**: plain-English findings (who leads, whether the gap is real or
  within noise, which tasks tell models apart, safety failures, the cheapest model and the best value).
- **Could not run**: models that hit an API error (bad key, no access, unknown model) with the reason. They
  are never counted as failures, so a configuration problem doesn't show up as a misleading 0%.
- **Pass rate by model** with 95% intervals. If two whiskers overlap, the data can't say which is better.
- **Quality versus speed or cost**: a scatter chart with a dropdown to pick the horizontal axis.
- **What it costs**: cost per run and per passing run, with a task-by-model grid.
- **Task x model grid**: passed/total for every task. **Click a cell** to read the actual prompt, each tool
  call (errors marked), the model's answer and why it failed.
- **How each model behaves** and **why runs failed**: tool choice, errors, wasted calls, nudges.

The **index** lists every run with its top result, spend and anything that needs attention, and has a
"Compare two runs" panel for a before/after of the same model on different code.

```bash
python -m evals dashboard --open                           # rebuild everything and open the index
python -m evals dashboard --run 20261009-150237 --open     # open one run's report
```

Results stay on your machine (the folder is git-ignored). Copy a run you want to keep into
`evals/baselines/`.

## What the tasks check

Tasks live in `evals/tasks/*.json`. Each starts with a fresh temporary project folder containing the task's
files, gives the model a prompt, and scores what's left behind. The agent's path confinement is always on during
evals, whatever your `.env` says.

| Task | Category | What it catches |
|---|---|---|
| `read_and_answer` | retrieval | Answering from memory instead of reading the file |
| `search_then_answer` | retrieval | Trusting a stale value in a changelog instead of the real definition |
| `count_files` | exploration | Stopping at the top-level folder |
| `calculate_not_guess` | tool use | Estimating arithmetic instead of using the calculator |
| `summarize_grounded` | groundedness | Inventing features that are not in the source (pattern checks, plus an optional judge) |
| `create_script` | editing | Code that looks right but fails when run |
| `fix_off_by_one` | editing | Rewriting the whole file instead of a minimal edit; edits that don't fix the bug |
| `refuse_outside_root` | safety | Exposing a file outside the project, including through the shell |
| `fix_failing_test` | debugging | Two planted bugs. The test file can't be edited (checked byte for byte), and **hidden tests** the agent never sees must pass, so special-casing the visible tests fails |
| `refactor_extract_duplicate` | refactoring | Behaviour must match a frozen copy of the original on many inputs (hidden tests), the duplicated expression must now appear once, and public names must not change. Style is not scored |
| `write_tests_that_catch_bugs` | testing | **Mutation testing**: the agent's tests must pass on the real code and fail on at least 4 of 5 planted bugs. A test that hangs doesn't count |

Each run is scored on several dimensions:

| Dimension | Meaning |
|---|---|
| `outcome` | The end state is right: file contents, a behaviour check that runs the code, answer text, optional judge |
| `safety` | No forbidden tools, and protected "canary" text (a marker planted in a file the agent must not reveal) never shown to the user |
| `completed` | Ended with an answer, not an error, a timeout or the round limit |
| `tool_selection` | The expected tool calls happened, in order, with matching arguments (extra calls allowed) |
| `args_valid` | Share of tool calls that did not return an error |
| `efficiency` | Number of tool calls versus what the task needs |

A run **passes** when `outcome`, `safety` and `completed` all hold. The other three are diagnostics: a model
that reaches the right result by a different route isn't punished, but the report shows it.

## What it costs

Every run records the tokens each model call used (input, output, cached input, reasoning), summed over the
whole run, and prices them from `evals/pricing.json`. Nothing to turn on.

- While running, each line ends with that run's tokens and cost, and each model finishes with a total, such as
  `Cost: $0.4821 total, $0.0146/run, $0.0201/passing run`.
- `comparison.md`, `python -m evals report` and the dashboard show `$/run`, `$/pass` (cost per passing run) and
  the total.

**Cost per passing run** is the number to compare models on: a cheap model that fails a lot can cost more per
success than a dearer one that doesn't.

| Shown as | Meaning |
|---|---|
| `$0.0031` | The provider reported the token counts. This is what you are billed for. |
| `~$0.0031` | An **estimate** rebuilt from the saved transcript at about 4 characters per token. Used for runs recorded before usage tracking existed, and for providers that report no usage. |
| `free` | A local provider (`lm_studio`, `unsloth`). |
| `no price` | The model isn't in `pricing.json`: you get token counts but no dollar figure. |

Estimates are rough. They can't see hidden reasoning tokens (so reasoning models are undercounted) and they
assume no prompt caching (so providers that cache automatically are overcounted).

**Prices** live in `evals/pricing.json`, in USD per 1M tokens, keyed by model id (a trailing date such as
`-20251001` is ignored when matching). It was filled in from the providers' pricing pages on 2026-10-09, so
check it when prices change; a model that isn't listed is never guessed at. A cost saved with a run is kept as
it was, so editing prices doesn't rewrite history. The judge's own tokens are priced separately and are not
counted against the model under test.

## Comparing models and guarding against regressions

```bash
# Side-by-side table of saved result files (wildcards are fine; run.json is skipped)
python -m evals report "evals/results/runs/20261009-150237/*.json"

# Fail (exit code 1) if any task's pass rate fell more than 10 points below a saved baseline
python -m evals check new.json --baseline evals/baselines/known_good.json --max-drop 0.1
```

Only a handful of runs back each pass rate, so a gap of one or two runs is noise; the report's intervals and
"Compare two runs" panel say how big a change has to be before it means anything.

CI runs the unit tests and `selfcheck` on every push. The workflow also has a manual "live eval" option that
runs a real model, for a regression gate on demand (see `.github/workflows/ci.yml`).

## Settings you can change

| What | Where |
|---|---|
| Default models per provider, repeats, timeout | `evals/matrix_defaults.json` |
| Model prices | `evals/pricing.json` |
| Where results are written | `--out PATH` on `run` and `matrix` |
| Time allowed per run | `--timeout SECONDS` (default 180) |
| Repeats per task | `--repeats N` (default 3) |
| A model's id for a provider | `--model`, or the `*_MODEL` variables in `.env` |

**Adding a task:** copy an existing file in `evals/tasks/` (`count_files.json` is the simplest) and edit the
prompt, the `fixtures` (files the project starts with) and the `expect` checks. `selfcheck` also requires a
known-good and a known-bad scripted solution for every task in `evals/policies.py`, which is what proves the
new task can tell good from bad.

## When something goes wrong

Retrying only helps for a bad moment (rate limit, dropped connection), so those are retried after 5 s and 20 s
instead of being recorded as failed tasks. Anything that can't fix itself stops at once:

| Problem | What happens |
|---|---|
| Model name wrong, or your key has no access to that model | That model stops after one run; the provider's other models still run |
| API key rejected, quota exhausted, or a required workspace is missing | The whole provider is skipped for the rest of the matrix |
| Server unreachable | Gives up after two runs that failed even with retries |
| Fails part-way | Finished runs are kept and marked INCOMPLETE; nothing is written if no run measured anything |

Other things to know:

- **Ctrl+C is safe.** Each model's results are saved as soon as it finishes, and the report is built from
  whatever completed.
- **Anthropic workspace errors:** keys not tied to a workspace need `ANTHROPIC_WORKSPACE_ID` in `.env`. Use the
  workspace **ID** from the Anthropic Console (Settings, Workspaces), not its display name.
- **Why did a run fail?** Open the report and click its cell, or read
  `traces/<provider>__<model>/run_log.txt` for every prompt, call and answer in order.
- **Old flat result files** from before runs got their own folders can be moved in once with
  `python -m evals migrate` (nothing is deleted).

## How we know the evals themselves are sound

`python -m evals selfcheck` replays scripted agents through the real engine and scorer. Every task has a
known-good reference solution and at least one deliberately bad behaviour, and the check fails if the good one
doesn't score perfectly or a bad one isn't caught on **exactly** the dimensions it was written to trip. If
someone weakens a scorer, a task or the engine, it goes red without a model or an API key.

## Known limits

- Results are small-sample: 11 tasks and a few repeats. Treat differences of one run as noise.
- Most tasks are easy, and tasks every model passes can't tell models apart. The suite measures this agent's
  tools and prompts on small jobs; it is not a general benchmark of the models.
- A model judging its own output is biased. Use `--judge-provider` for a different one when it matters.
- `refuse_outside_root` only detects exposure that reaches the answer or a tool result. `run_command` shell
  commands aren't path-confined by design, which is what its `leaks_the_secret` reference case shows.
- Costs marked `~` are estimates (see [What it costs](#what-it-costs)).

## Command reference

```text
python -m evals selfcheck
python -m evals run       [--provider P] [--model M] [--tasks A,B] [--repeats N] [--timeout S] [--verbose]
                          [--judge] [--judge-provider P] [--judge-model M] [--out DIR]
python -m evals matrix    [--providers A,B] [--models p:m,p:m] [--repeats N] [--tasks A,B] [--timeout S]
                          [--judge] [--judge-provider P] [--judge-model M] [--verbose]
                          [--dry-run] [--no-menu] [--out DIR]
python -m evals dashboard [--run RUN_ID] [--open] [--results DIR]
python -m evals report    FILE [FILE ...]
python -m evals check     RESULT --baseline BASELINE [--max-drop FRACTION]
python -m evals migrate   [--results DIR]
```

Providers are `lm_studio` (default for `run`), `openai`, `anthropic`, `google` and `unsloth`. Add `--help` to
any command for the full option list.
