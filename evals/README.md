# Agent evals

An evaluation harness for the tool-calling agent in this repo. It answers two different questions:

1. **Does the agent harness still work?** (`pytest`, `python -m evals selfcheck`: no model needed)
2. **How reliably does a given model use it?** (`python -m evals run`: needs LM Studio or OpenAI)

## Why this exists

A demo that works once says little about an agent. Models are non-deterministic, so one pass
proves nothing; and a correct final answer can hide a wrong route (guessing instead of reading,
rewriting a whole file instead of a minimal edit, leaking a file through the shell). Each task here is
scored on several dimensions and repeated, so differences between models and between code changes
show up as numbers.

## What a task checks

Tasks live in `evals/tasks/*.json`. Each runs the real chat engine in a throwaway project folder.

| Dimension | Meaning |
|---|---|
| `tool_selection` | Expected tool calls happened, in order, with matching arguments (extra calls allowed) |
| `args_valid` | Fraction of tool calls that did not return an error |
| `outcome` | End state is right: file contents, a behaviour check that actually runs the code, answer text, optional LLM judge |
| `efficiency` | Number of tool calls versus what the task needs |
| `safety` | No forbidden tools; protected "canary" text never shown to the user |
| `completed` | Ended with an answer, not an error or the round limit |

A run **passes** when `outcome`, `safety` and `completed` all hold. The other dimensions are diagnostics,
so a model that reaches the right result a different way is not punished, but the report shows it.

| Task | Category | What it catches |
|---|---|---|
| `read_and_answer` | retrieval | answering from memory instead of reading the file |
| `search_then_answer` | retrieval | trusting a stale value in a changelog instead of the real definition |
| `fix_off_by_one` | editing | rewriting the whole file instead of a minimal edit; edits that don't fix the bug |
| `create_script` | editing | code that looks right but fails when run |
| `calculate_not_guess` | tool use | estimating arithmetic instead of using the calculator |
| `count_files` | exploration | stopping at the top-level folder |
| `refuse_outside_root` | safety | exposing a file outside the project, including through the shell |
| `summarize_grounded` | groundedness | inventing features not in the source (regex checks, plus optional judge) |

## Testing the tests

`python -m evals selfcheck` replays scripted agents through the real engine and scorer. Every task has a
known-good reference solution and at least one deliberately bad behaviour. The check fails if the good one
doesn't score perfectly, or if a bad one isn't caught on **exactly** the dimensions it was written to trip.
If someone weakens a scorer, a task, or the engine, this goes red without a model or API key.
It runs in CI on every push.

## Running against a real model

```bash
# LM Studio: load a model, start the local server, then
python -m evals run --provider lm_studio --repeats 3

# OpenAI
export OPENAI_API_KEY=...    # PowerShell: $env:OPENAI_API_KEY = "..."
python -m evals run --provider openai --model gpt-4o-mini --repeats 3

# Grade rubric tasks with an LLM judge (ideally a different model than the one being tested)
python -m evals run --provider lm_studio --judge --judge-provider openai --judge-model gpt-4o-mini
```

Each run writes `evals/results/<time>__<provider>__<model>.json` plus a full transcript per run under
`evals/results/traces/` (these stay local; the folder is git-ignored). Compare models side by side and
gate on regressions:

```bash
python -m evals report evals/results/*.json
python -m evals check new.json --baseline evals/baselines/known_good.json --max-drop 0.1
```

Copy results worth keeping into `evals/baselines/`.

A single model has to be loaded at a time in LM Studio, so run once per model and compare the files afterwards.

## Known limits

- The local-model results are small-sample: 8 tasks, a handful of repeats. Treat differences of one run as noise.
- A model judging its own output is biased; use `--judge-provider` for a different one when it matters.
- `refuse_outside_root` can only detect exposure that reaches the answer or a tool result. `run_command` runs
  shell commands that aren't path-confined by design, which is what the `leaks_the_secret` reference case shows.
- The live (`run`) path is exercised in tests with a scripted provider; its behaviour against real models
  depends on the model.
