"""Run folders, the US date format, the migration, and the generated pages."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from evals.dashboard import build_all, model_summary, run_summary, write_index, write_run_dashboard
from evals.migrate import migrate_legacy
from evals.report import build_result
from evals.runner import RunRecord
from evals.runs import (
    ensure_gitignore,
    format_us,
    is_infra_error,
    legacy_result_files,
    list_run_dirs,
    new_run_dir,
    read_manifest,
    result_files,
    write_manifest,
)


def record(task_id, passed, error=None, **extra):
    scores = {k: 1.0 for k in ("tool_selection", "args_valid", "outcome", "efficiency", "safety", "completed")}
    return RunRecord(task_id, 0, passed, scores, [], None, [], 1, "an answer </script> with markup", 1.0, error=error, extra=extra)


def make_result(model, timestamp, provider="openai", records=None, **meta):
    records = records or [record("read_and_answer", True), record("count_files", False)]
    return build_result(records, {"provider": provider, "model": model, "repeats": 1, "timestamp": timestamp, "git_sha": "abc123", **meta})


def save_in_run(run_dir: Path, result: dict, name: str):
    (run_dir / name).write_text(json.dumps(result), encoding="utf-8")


# ---- US date format ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "run_id, expected",
    [
        ("20261009-150237", "10/09/2026 3:02 PM"),
        ("20261009-000500", "10/09/2026 12:05 AM"),
        ("20261009-120000", "10/09/2026 12:00 PM"),
        ("20260102-093000", "01/02/2026 9:30 AM"),
        ("20261231-235959", "12/31/2026 11:59 PM"),
        ("20261009-150237-2", "10/09/2026 3:02 PM"),  # a second run in the same second
        ("not-a-date", "not-a-date"),
    ],
)
def test_run_ids_are_shown_as_us_dates_with_a_12_hour_clock(run_id, expected):
    assert format_us(run_id) == expected


# ---- run folders -----------------------------------------------------------------------------


def test_each_run_gets_its_own_timestamped_folder_and_never_reuses_one(tmp_path, monkeypatch):
    monkeypatch.setattr("time.strftime", lambda fmt: "20261009-150237")
    first, second, third = new_run_dir(tmp_path), new_run_dir(tmp_path), new_run_dir(tmp_path)
    assert [d.name for d in (first, second, third)] == ["20261009-150237", "20261009-150237-2", "20261009-150237-3"]
    assert all(d.parent == tmp_path / "runs" and d.is_dir() for d in (first, second, third))


def test_results_stay_out_of_git_without_clobbering_an_existing_ignore_file(tmp_path):
    (tmp_path / ".gitignore").write_text("*.json\ntraces/\n", encoding="utf-8")
    ensure_gitignore(tmp_path)
    lines = (tmp_path / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert {"*.json", "traces/", "runs/", "index.html", "*.md"} <= set(lines) and lines.count("*.json") == 1


def test_manifest_merges_updates_and_survives_corruption(tmp_path):
    write_manifest(tmp_path, kind="matrix", status="running", repeats=3)
    write_manifest(tmp_path, status="complete")
    assert read_manifest(tmp_path) | {} == {"id": tmp_path.name, "kind": "matrix", "status": "complete", "repeats": 3}
    (tmp_path / "run.json").write_text("{broken", encoding="utf-8")
    assert read_manifest(tmp_path)["status"] == "unknown"


def test_run_folders_list_newest_first_and_ignore_stray_files(tmp_path):
    for name in ("20261008-100000", "20261009-150237", "20261009-090000"):
        (tmp_path / "runs" / name).mkdir(parents=True)
    (tmp_path / "runs" / "notes.txt").write_text("x", encoding="utf-8")
    assert [d.name for d in list_run_dirs(tmp_path)] == ["20261009-150237", "20261009-090000", "20261008-100000"]
    assert list_run_dirs(tmp_path / "nowhere") == []


def test_result_files_skip_the_manifest_and_non_results(tmp_path):
    save_in_run(tmp_path, make_result("b", "20261009-150300"), "openai__b.json")
    save_in_run(tmp_path, make_result("a", "20261009-150200"), "openai__a.json")
    write_manifest(tmp_path, status="complete")
    (tmp_path / "other.json").write_text('{"x": 1}', encoding="utf-8")
    assert [r["meta"]["model"] for r in result_files(tmp_path)] == ["a", "b"]


def test_api_errors_are_recognised_as_infrastructure_not_model_failures():
    assert is_infra_error("PermissionDeniedError: 403 no access") and is_infra_error("BadRequestError: workspace")
    assert not is_infra_error("ValueError: boom") and not is_infra_error(None) and not is_infra_error("")


def test_a_models_summary_leaves_out_runs_that_died_on_api_errors():
    result = make_result("m", "20261009-150237", records=[record("read_and_answer", True), record("read_and_answer", False),
                                                             record("count_files", False, error="RateLimitError: x")])
    s = model_summary(result)
    assert (s["n"], s["passed"], s["errored"]) == (2, 1, 1)
    assert s["per_task"]["count_files"] == [0, 0]


# ---- the pages -------------------------------------------------------------------------------


def make_run(results_dir, run_id, models, **manifest):
    run_dir = results_dir / "runs" / run_id
    run_dir.mkdir(parents=True)
    for name, ts in models:
        save_in_run(run_dir, make_result(name, ts), f"openai__{name}.json")
    write_manifest(run_dir, kind="matrix", status="complete", started="2026-10-09T15:02:37", finished="2026-10-09T15:12:37",
                   git_sha="abc123", repeats=1, tasks=["read_and_answer", "count_files"], **manifest)
    return run_dir


def test_the_index_lists_runs_newest_first_with_us_dates(tmp_path):
    make_run(tmp_path, "20261008-100000", [("m1", "20261008-100000")])
    make_run(tmp_path, "20261009-150237", [("m1", "20261009-150237"), ("m2", "20261009-150300")])
    index = write_index(tmp_path)
    payload = json.loads(re.search(r'<script type="application/json" id="data">(.*?)</script>', index.read_text(encoding="utf-8"), re.S).group(1))
    assert [r["id"] for r in payload["runs"]] == ["20261009-150237", "20261008-100000"]
    assert [r["label"] for r in payload["runs"]] == ["10/09/2026 3:02 PM", "10/08/2026 10:00 AM"]
    assert payload["runs"][0]["href"] == "runs/20261009-150237/dashboard.html"
    assert payload["runs"][0]["seconds"] == 600 and len(payload["runs"][0]["models"]) == 2


def test_each_run_gets_its_own_report_that_links_back_to_the_index(tmp_path):
    run_dir = make_run(tmp_path, "20261009-150237", [("m1", "20261009-150237")])
    page = write_run_dashboard(run_dir)
    html = page.read_text(encoding="utf-8")
    payload = json.loads(re.search(r'<script type="application/json" id="data">(.*?)</script>', html, re.S).group(1))
    assert page == run_dir / "dashboard.html" and payload["indexHref"] == "../../index.html"
    assert payload["run"]["label"] == "10/09/2026 3:02 PM" and payload["run"]["folder"] == str(run_dir)
    assert len(payload["results"]) == 1 and payload["tasks"]["read_and_answer"]["category"] == "retrieval"


def test_embedded_data_cannot_break_out_of_its_script_tag(tmp_path):
    run_dir = make_run(tmp_path, "20261009-150237", [("m1", "20261009-150237")])
    html = write_run_dashboard(run_dir).read_text(encoding="utf-8")
    payload = re.search(r'<script type="application/json" id="data">(.*?)</script>', html, re.S).group(1)
    assert "</script>" not in payload  # the stored answer text contained one
    assert json.loads(payload)["results"][0]["tasks"]["read_and_answer"]["runs"][0]["answer"].endswith("with markup")
    assert "__EVAL_DATA__" not in html


def test_pages_are_self_contained(tmp_path):
    make_run(tmp_path, "20261009-150237", [("m1", "20261009-150237")])
    index, pages = build_all(tmp_path)
    for path in [index, *pages]:
        html = path.read_text(encoding="utf-8")
        assert "http://" not in html.replace("http://www.w3.org/2000/svg", "") and "src=" not in html and "<link" not in html


def test_nothing_is_built_when_there_are_no_runs(tmp_path):
    assert build_all(tmp_path) == (None, [])


def test_run_summary_reports_problems_for_the_index(tmp_path):
    run_dir = make_run(tmp_path, "20261009-150237", [("m1", "20261009-150237")], not_run=[{"model": "anthropic:x", "reason": "no key"}])
    s = run_summary(run_dir)
    assert s["not_run"] == [{"model": "anthropic:x", "reason": "no key"}] and s["status"] == "complete" and s["tasks"] == ["read_and_answer", "count_files"]


def test_the_dashboard_command_builds_the_index_and_can_open_one_run(tmp_path, capsys):
    import evals.__main__ as cli

    assert cli.main(["dashboard", "--results", str(tmp_path)]) == 1 and "No runs found" in capsys.readouterr().out
    make_run(tmp_path, "20261009-150237", [("m1", "20261009-150237")])
    assert cli.main(["dashboard", "--results", str(tmp_path)]) == 0 and (tmp_path / "index.html").exists()
    assert cli.main(["dashboard", "--results", str(tmp_path), "--run", "20261009-150237"]) == 0
    assert cli.main(["dashboard", "--results", str(tmp_path), "--run", "nope"]) == 2


# ---- migrating the old flat layout ------------------------------------------------------------


def legacy(results, name, model, ts, provider="openai"):
    (results).mkdir(parents=True, exist_ok=True)
    stem = f"{ts}__{provider}__{model}"
    (results / f"{stem}.json").write_text(json.dumps(make_result(model, ts, provider)), encoding="utf-8")
    trace = results / "traces" / stem
    trace.mkdir(parents=True)
    (trace / "run_log.txt").write_text("log", encoding="utf-8")
    return stem


def test_old_flat_results_are_grouped_into_runs_by_start_time(tmp_path):
    # a matrix run of three models a minute apart, then a later single run
    legacy(tmp_path, "a", "m1", "20261009-140000")
    legacy(tmp_path, "b", "m2", "20261009-140100")
    legacy(tmp_path, "c", "m3", "20261009-140230", provider="anthropic")
    legacy(tmp_path, "d", "m4", "20261009-160000")
    (tmp_path / "matrix_20261009-140300.md").write_text("| table |", encoding="utf-8")
    (tmp_path / "dashboard.html").write_text("old", encoding="utf-8")

    assert migrate_legacy(tmp_path, say=lambda *_: None) == 4

    runs = {d.name: d for d in list_run_dirs(tmp_path)}
    assert sorted(runs) == ["20261009-140000", "20261009-160000"]
    first = runs["20261009-140000"]
    assert sorted(p.name for p in first.glob("*.json")) == ["anthropic__m3.json", "openai__m1.json", "openai__m2.json", "run.json"]
    assert (first / "traces" / "openai__m1" / "run_log.txt").read_text(encoding="utf-8") == "log"
    assert (first / "comparison.md").read_text(encoding="utf-8") == "| table |"  # the matrix table joined its run
    manifest = read_manifest(first)
    assert manifest["kind"] == "migrated" and manifest["targets"] == ["openai:m1", "openai:m2", "anthropic:m3"]
    assert manifest["started"] == "2026-10-09T14:00:00" and manifest["git_sha"] == "abc123"
    assert not legacy_result_files(tmp_path) and not (tmp_path / "dashboard.html").exists()
    assert not list((tmp_path / "traces").glob("*")), "old trace folders were moved, not copied"


def test_migration_is_safe_to_run_twice_and_with_nothing_to_do(tmp_path):
    assert migrate_legacy(tmp_path, say=lambda *_: None) == 0
    legacy(tmp_path, "a", "m1", "20261009-140000")
    assert migrate_legacy(tmp_path, say=lambda *_: None) == 1
    assert migrate_legacy(tmp_path, say=lambda *_: None) == 0
    assert len(list_run_dirs(tmp_path)) == 1


def test_migrated_runs_show_up_in_the_index(tmp_path):
    legacy(tmp_path, "a", "m1", "20261009-140000")
    migrate_legacy(tmp_path, say=lambda *_: None)
    index, pages = build_all(tmp_path)
    assert index and len(pages) == 1 and "10/09/2026 2:00 PM" in index.read_text(encoding="utf-8")
