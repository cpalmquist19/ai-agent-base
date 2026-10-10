"""Run the evals across many providers and models with one command.

    python -m evals matrix                      # interactive menu
    python -m evals matrix --providers openai,anthropic       # each provider's default models
    python -m evals matrix --models openai:gpt-5.6-terra,anthropic:claude-sonnet-5-5 --repeats 5
    python -m evals matrix --dry-run            # show the plan, run nothing

Every model gets its own result file as soon as it finishes, so an interrupted run keeps what
completed. A model that can't be reached is reported and skipped; it doesn't stop the others.
"""

from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

PROVIDERS = ("openai", "anthropic", "google", "lm_studio", "unsloth")
# Cloud providers and the environment variable that holds their key.
API_KEY_VARS = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "google": "GOOGLE_AI_STUDIO_API_KEY",
}
LOADED = "(loaded)"  # local servers: use whichever model is currently loaded
DEFAULTS_PATH = Path(__file__).parent / "matrix_defaults.json"
_BUILTIN_DEFAULTS: dict[str, Any] = {
    "repeats": 3,
    "timeout": 180,
    "defaults": {"openai": [], "anthropic": [], "google": [], "lm_studio": [LOADED], "unsloth": [LOADED]},
    "also_offered": {},
}

Target = tuple[str, "str | None"]  # (provider, model id; None = whichever model is loaded)


@dataclass
class Plan:
    targets: list[Target]
    repeats: int = 3
    tasks: list[str] | None = None
    timeout: float = 180
    judge: bool = False
    judge_provider: str | None = None
    judge_model: str | None = None


@dataclass
class Outcome:
    results: list[dict[str, Any]] = field(default_factory=list)
    failures: list[tuple[str, str]] = field(default_factory=list)
    interrupted: bool = False
    report_path: Path | None = None
    run_dir: Path | None = None

    @property
    def exit_code(self) -> int:
        return 130 if self.interrupted else (1 if self.failures else 0)


# ------------------------------------------------------------------ defaults and parsing


def load_defaults(path: Path = DEFAULTS_PATH) -> dict[str, Any]:
    merged = json.loads(json.dumps(_BUILTIN_DEFAULTS))
    try:
        merged.update(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        pass
    return merged


def label(provider: str, model: str | None) -> str:
    return f"{provider}:{model or 'loaded'}"


def _split(text: str | None) -> list[str]:
    return [part.strip() for part in (text or "").split(",") if part.strip()]


def parse_targets(items: list[str]) -> list[Target]:
    """'openai:gpt-5.6-terra' -> ('openai', 'gpt-5.6-terra'); 'lm_studio' or 'lm_studio:loaded' -> loaded model."""
    targets: list[Target] = []
    for item in items:
        provider, _, model = item.partition(":")  # model ids may contain ':', so split once
        provider = provider.strip().lower()
        if provider not in PROVIDERS:
            raise ValueError(f"unknown provider {provider!r} in {item!r}; choose from {', '.join(PROVIDERS)}")
        model = model.strip()
        target = (provider, None if model.lower() in ("", "loaded", LOADED) else model)
        if target not in targets:
            targets.append(target)
    return targets


def default_targets(providers: list[str], defaults: dict[str, Any]) -> list[Target]:
    items: list[str] = []
    for provider in providers:
        if provider not in PROVIDERS:
            raise ValueError(f"unknown provider {provider!r}; choose from {', '.join(PROVIDERS)}")
        models = defaults["defaults"].get(provider) or [LOADED]
        items += [f"{provider}:{m}" for m in models]
    return parse_targets(items)


def plan_from_args(args: Any, defaults: dict[str, Any]) -> Plan | None:
    """A plan from command-line options, or None if neither --providers nor --models was given."""
    if not args.providers and not args.models:
        return None
    targets = parse_targets(_split(args.models))
    for target in default_targets(_split(args.providers), defaults):
        if target not in targets:
            targets.append(target)
    return Plan(
        targets=targets,
        repeats=args.repeats or defaults["repeats"],
        tasks=_split(args.tasks) or None,
        timeout=args.timeout or defaults["timeout"],
        judge=args.judge,
        judge_provider=args.judge_provider,
        judge_model=args.judge_model,
    )


# ------------------------------------------------------------------ talking to the providers


def _endpoint(provider: str) -> tuple[str, str]:
    env = os.environ
    return {
        "openai": (env.get("OPENAI_BASE_URL", "https://api.openai.com/v1"), env.get("OPENAI_API_KEY", "")),
        "anthropic": (env.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com/v1"), env.get("ANTHROPIC_API_KEY", "")),
        "google": (
            env.get("GOOGLE_AI_STUDIO_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/"),
            env.get("GOOGLE_AI_STUDIO_API_KEY", ""),
        ),
        "lm_studio": (env.get("LM_STUDIO_BASE_URL", "http://localhost:1234/v1"), env.get("LM_STUDIO_API_KEY", "lm-studio")),
        "unsloth": (env.get("UNSLOTH_BASE_URL", "http://127.0.0.1:8000/v1"), env.get("UNSLOTH_API_KEY", "sk-no-key-required")),
    }[provider]


def remote_models(provider: str, timeout: float = 5.0) -> list[str]:
    """Model ids the provider says it offers. Empty if unreachable, unauthorised, or unsupported."""
    try:
        from openai import OpenAI

        base_url, key = _endpoint(provider)
        if not key:
            return []
        ids = sorted(m.id for m in OpenAI(base_url=base_url, api_key=key, timeout=timeout, max_retries=0).models.list().data)
    except Exception:
        return []
    skip = ("embed", "audio", "tts", "whisper", "image", "realtime", "transcribe", "moderation", "search", "instruct")
    if provider == "openai":
        ids = [i for i in ids if i.startswith(("gpt-", "o1", "o3", "o4", "chatgpt")) and not any(s in i for s in skip)]
    elif provider == "google":  # ids come back as "models/gemini-..."; callers pass them without the prefix
        ids = [i.removeprefix("models/") for i in ids]
        ids = [i for i in ids if i.startswith(("gemini", "gemma")) and not any(s in i for s in (*skip, "live", "robotics", "computer-use", "banana", "translate"))]
    elif provider in ("lm_studio", "unsloth"):
        ids = [i for i in ids if "embed" not in i]
    return ids


def provider_status(provider: str) -> tuple[bool, str]:
    if provider in API_KEY_VARS:
        var = API_KEY_VARS[provider]
        return (True, f"{var} found") if os.environ.get(var) else (False, f"no {var} in the environment or .env")
    models = remote_models(provider, timeout=2.0)
    return (True, f"reachable, {len(models)} model(s)") if models else (False, "server not reachable")


# ------------------------------------------------------------------ the menu


def _parse_selection(text: str, options: list[str], allow_custom: bool) -> list[str] | None:
    """'1,3' -> options 1 and 3; with allow_custom, other words are taken literally. None = invalid."""
    picked: list[str] = []
    for token in _split(text):
        if token.isdigit():
            index = int(token)
            if not 1 <= index <= len(options):
                return None
            value = options[index - 1]
        elif allow_custom:
            value = token
        else:
            return None
        if value not in picked:
            picked.append(value)
    return picked


def _choose(
    ask: Callable[[str], str],
    say: Callable[[str], None],
    prompt: str,
    options: list[str],
    default: list[str],
    allow_custom: bool = False,
) -> list[str]:
    default_text = ",".join(str(options.index(d) + 1) for d in default if d in options) or "none"
    while True:
        answer = ask(f"{prompt} [{default_text}]: ").strip()
        if not answer:
            if default:
                return default
            say("  Please choose at least one.")
            continue
        picked = _parse_selection(answer, options, allow_custom)
        if picked:
            return picked
        say("  Didn't understand that. Use numbers like 1,3" + (" or type names." if allow_custom else "."))


def _ask_number(ask: Callable[[str], str], say: Callable[[str], None], prompt: str, default: float, cast: type) -> Any:
    while True:
        answer = ask(f"{prompt} [{default:g}]: ").strip()
        if not answer:
            return cast(default)
        try:
            value = cast(answer)
            if value > 0:
                return value
        except ValueError:
            pass
        say("  Please enter a positive number.")


def interactive_plan(
    defaults: dict[str, Any],
    *,
    ask: Callable[[str], str] = input,
    say: Callable[[str], None] = print,
    status: Callable[[str], tuple[bool, str]] | None = None,
    list_models: Callable[[str], list[str]] | None = None,
    preset: Plan | None = None,
    available_tasks: list[str] | None = None,
) -> Plan | None:
    status = status or provider_status  # looked up at call time so tests (and callers) can replace them
    list_models = list_models or remote_models
    say("\nEval matrix: pick what to run. Press Enter to accept the value in [brackets].\n")
    say("Providers:")
    statuses = {p: status(p) for p in PROVIDERS}
    for number, provider in enumerate(PROVIDERS, 1):
        ok, note = statuses[provider]
        say(f"  {number}) {provider:<10} {'ready' if ok else 'not ready':<9} {note}")
    ready = [p for p in PROVIDERS if statuses[p][0]]
    providers = _choose(ask, say, "Providers (numbers, e.g. 1,2)", list(PROVIDERS), ready)

    targets: list[Target] = []
    for provider in providers:
        suggested = defaults["defaults"].get(provider) or [LOADED]
        extra = [m for m in defaults.get("also_offered", {}).get(provider, []) if m not in suggested]
        found = [m for m in list_models(provider) if m not in suggested and m not in extra] if statuses[provider][0] else []
        options = suggested + extra + found
        say(f"\nModels for {provider} (* = default):")
        for number, model in enumerate(options, 1):
            say(f"  {number}) {'*' if model in suggested else ' '}{model}")
        say("  Type model names to use ones not listed.")
        chosen = _choose(ask, say, f"{provider} models", options, suggested, allow_custom=True)
        targets += [(provider, None if m in (LOADED, "loaded") else m) for m in chosen]

    say("")
    repeats = _ask_number(ask, say, "Repeats per task", (preset.repeats if preset else defaults["repeats"]), int)
    timeout = _ask_number(ask, say, "Seconds allowed per run", (preset.timeout if preset else defaults["timeout"]), float)
    tasks: list[str] | None = preset.tasks if preset else None
    if available_tasks:
        say("\nTasks: " + ", ".join(available_tasks))
        chosen_tasks = _split(ask("Tasks to run, comma-separated [all]: "))
        unknown = [t for t in chosen_tasks if t not in available_tasks]
        tasks = None if not chosen_tasks else [t for t in chosen_tasks if t in available_tasks]
        if unknown:
            say(f"  Ignoring unknown task(s): {', '.join(unknown)}")
    plan = Plan(targets=targets, repeats=repeats, tasks=tasks, timeout=timeout)
    say("")
    say(describe(plan, n_tasks=len(tasks or available_tasks or [])))
    if ask("Start? [Y/n]: ").strip().lower() in ("n", "no"):
        return None
    return plan


def describe(plan: Plan, n_tasks: int) -> str:
    runs = len(plan.targets) * n_tasks * plan.repeats
    lines = [f"Plan: {len(plan.targets)} model(s) x {n_tasks} task(s) x {plan.repeats} repeat(s) = {runs} runs"]
    lines += [f"  - {label(p, m)}" for p, m in plan.targets]
    if plan.tasks:
        lines.append(f"  tasks: {', '.join(plan.tasks)}")
    return "\n".join(lines)


# ------------------------------------------------------------------ running it


def run_matrix(
    plan: Plan,
    *,
    out: Path,
    verbose: bool,
    make_provider: Callable[[str, "str | None"], Any],
    run_model: Callable[..., Any] | None = None,
    sleep: Callable[[float], None] = time.sleep,
    say: Callable[[str], None] = print,
) -> Outcome:
    from evals.cost import cost_line
    from evals.execute import git_sha, run_model as default_run_model
    from evals.judge import LLMJudge
    from evals.report import render_markdown
    from evals.tasks import load_tasks

    run_model = run_model or default_run_model
    tasks = load_tasks(plan.tasks)
    outcome = Outcome()
    judge = None
    if plan.judge:
        try:
            jp = make_provider(plan.judge_provider or plan.targets[0][0], plan.judge_model if plan.judge_provider else plan.targets[0][1])
            judge = LLMJudge(jp.client, jp.model_id, omit_temperature=getattr(jp, "omit_temperature", False))
        except Exception as exc:
            say(f"Judge unavailable ({type(exc).__name__}: {exc}); rubric tasks will be skipped.")

    from evals.execute import ModelUnavailable

    from evals.runs import new_run_dir, write_manifest

    run_dir = new_run_dir(out)  # every matrix invocation gets its own timestamped folder
    outcome.run_dir = run_dir
    started = run_dir.name
    write_manifest(
        run_dir, kind="matrix", status="running", started=time.strftime("%Y-%m-%dT%H:%M:%S"), git_sha=git_sha(),
        repeats=plan.repeats, timeout=plan.timeout, tasks=[t["id"] for t in tasks],
        targets=[label(p, m) for p, m in plan.targets], command=" ".join(sys.argv[1:]) or "matrix",
    )
    say(f"Run folder: {run_dir}")
    blocked: dict[str, str] = {}  # provider -> why every one of its models would fail
    try:
        for index, (provider_id, model) in enumerate(plan.targets, 1):
            name = label(provider_id, model)
            say(f"\n=== [{index}/{len(plan.targets)}] {name} ===")
            if provider_id in blocked:
                reason = f"skipped, {provider_id} stopped earlier: {blocked[provider_id]}"
                outcome.failures.append((name, reason))
                say(f"  {reason}")
                continue
            try:
                provider = make_provider(provider_id, model)
            except Exception as exc:
                reason = f"{type(exc).__name__}: {exc}"
                outcome.failures.append((name, reason))
                say(f"  skipped: {reason}")
                continue
            try:
                result, path, _ = run_model(
                    provider, tasks, repeats=plan.repeats, timeout=plan.timeout, judge=judge,
                    out=run_dir, verbose=verbose, sleep=sleep, say=say,
                )
            except ModelUnavailable as exc:  # a wrong model name, bad key, no quota: don't keep calling it
                outcome.failures.append((name, exc.reason))
                if exc.scope == "provider":
                    blocked[provider_id] = exc.reason
                continue
            except Exception as exc:
                reason = f"{type(exc).__name__}: {exc}"
                outcome.failures.append((name, reason))
                say(f"  failed while running: {reason}")
                continue
            outcome.results.append(result)
            s = result["summary"]
            note = f" (INCOMPLETE: {result['meta']['aborted'][:120]})" if result["meta"].get("aborted") else ""
            spend = f", {cost_line(s['cost'])}" if s.get("cost") else ""
            say(f"  done: {s['pass_rate']:.0%} pass over {s['runs']} runs, {s['mean_duration_s']:.1f}s/run{spend} -> {path.name}{note}")
            if result["meta"].get("aborted"):
                outcome.failures.append((name, f"incomplete: {result['meta']['aborted']}"))
    except KeyboardInterrupt:
        outcome.interrupted = True
        say("\nInterrupted. Results for finished models were already saved; summarizing those.")

    say("")
    if outcome.results:
        table = render_markdown(outcome.results)
        say(table)
        body = [f"# Eval run {started}", "", f"git {git_sha()} | {len(tasks)} tasks x {plan.repeats} repeats", "", table]
        if outcome.failures:
            body += ["", "## Not run", *[f"- {n}: {why}" for n, why in outcome.failures]]
        outcome.report_path = run_dir / "comparison.md"
        outcome.report_path.write_text("\n".join(body) + "\n", encoding="utf-8")
        say(f"\nSaved comparison: {outcome.report_path}")
    else:
        say("No model finished, so there is nothing to compare.")
    status = "interrupted" if outcome.interrupted else "failed" if not outcome.results else "partial" if outcome.failures else "complete"
    write_manifest(run_dir, status=status, finished=time.strftime("%Y-%m-%dT%H:%M:%S"),
                   not_run=[{"model": n, "reason": why} for n, why in outcome.failures if not why.startswith("incomplete:")])
    try:  # fresh reports after every run; never let a reporting problem break the run
        from evals.dashboard import write_index, write_run_dashboard

        page = write_run_dashboard(run_dir)
        say(f"\nReport for this run: {page}")
        say(f"All runs:            {write_index(out)}   (or: python -m evals dashboard --open)")
    except Exception as exc:
        say(f"(Could not build the report: {type(exc).__name__}: {exc})")
    if outcome.failures:
        say("\nNot run:")
        for name, why in outcome.failures:
            say(f"  - {name}: {why}")
    return outcome


def cmd_matrix(
    args: Any,
    *,
    ask: Callable[[str], str] = input,
    say: Callable[[str], None] = print,
    make_provider: Callable[[str, "str | None"], Any] | None = None,
    interactive: bool | None = None,
) -> int:
    from evals.__main__ import RESULTS_DIR, _live_provider
    from evals.tasks import load_tasks

    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass

    defaults = load_defaults()
    all_tasks = [t["id"] for t in load_tasks()]
    try:
        plan = plan_from_args(args, defaults)
    except ValueError as exc:
        say(f"Error: {exc}")
        return 2
    if plan is None:
        interactive = sys.stdin.isatty() and not args.no_menu if interactive is None else interactive
        if interactive:
            preset = Plan(
                targets=[], repeats=args.repeats or defaults["repeats"], timeout=args.timeout or defaults["timeout"],
                tasks=_split(args.tasks) or None,
            )
            plan = interactive_plan(defaults, ask=ask, say=say, preset=preset, available_tasks=all_tasks)
            if plan is None:
                say("Cancelled.")
                return 0
        else:  # no terminal and no options: run each ready provider's default models
            ready = [p for p in PROVIDERS if provider_status(p)[0]]
            plan = Plan(
                targets=default_targets(ready, defaults),
                repeats=args.repeats or defaults["repeats"],
                tasks=_split(args.tasks) or None,
                timeout=args.timeout or defaults["timeout"],
            )
    if not plan.targets:
        say("Nothing to run: no ready providers. Set OPENAI_API_KEY / ANTHROPIC_API_KEY / GOOGLE_AI_STUDIO_API_KEY, start LM Studio, or pass --models.")
        return 1
    if args.judge:
        plan.judge, plan.judge_provider, plan.judge_model = True, args.judge_provider, args.judge_model
    say(describe(plan, n_tasks=len(plan.tasks or all_tasks)))
    if args.dry_run:
        return 0
    outcome = run_matrix(
        plan, out=Path(args.out or RESULTS_DIR), verbose=args.verbose,
        make_provider=make_provider or _live_provider, say=say,
    )
    return outcome.exit_code
