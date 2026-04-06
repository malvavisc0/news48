import json

from typer.testing import CliRunner

from main import app

runner = CliRunner()


def test_plans_list_show_cancel(tmp_path, monkeypatch):
    from agents.tools import planner as planner_tools

    monkeypatch.setattr(planner_tools, "_PLANS_DIR", tmp_path / ".plans")

    created = json.loads(
        planner_tools.create_plan(
            "test",
            "Task",
            ["Step 1", "Verify"],
            ["Condition 1", "Condition 2"],
        )
    )["result"]
    plan_id = created["plan_id"]

    list_result = runner.invoke(app, ["plans", "list", "--json"])
    assert list_result.exit_code == 0
    assert any(
        item["plan_id"] == plan_id for item in json.loads(list_result.stdout)
    )

    show_result = runner.invoke(app, ["plans", "show", plan_id, "--json"])
    assert show_result.exit_code == 0
    assert json.loads(show_result.stdout)["id"] == plan_id

    cancel_result = runner.invoke(app, ["plans", "cancel", plan_id, "--json"])
    assert cancel_result.exit_code == 0
    assert json.loads(cancel_result.stdout)["status"] == "failed"


def test_plans_show_displays_success_conditions(tmp_path, monkeypatch):
    from agents.tools import planner as planner_tools

    monkeypatch.setattr(planner_tools, "_PLANS_DIR", tmp_path / ".plans")

    created = json.loads(
        planner_tools.create_plan(
            "test",
            "Fetch all feeds",
            ["Fetch", "Verify"],
            ["All 55 feeds fetched", "Error rate below 5%"],
        )
    )["result"]
    plan_id = created["plan_id"]

    show_result = runner.invoke(app, ["plans", "show", plan_id])
    assert show_result.exit_code == 0
    assert "Success Conditions:" in show_result.stdout
    assert "All 55 feeds fetched" in show_result.stdout
    assert "Error rate below 5%" in show_result.stdout


def test_plans_show_json_includes_success_conditions(tmp_path, monkeypatch):
    from agents.tools import planner as planner_tools

    monkeypatch.setattr(planner_tools, "_PLANS_DIR", tmp_path / ".plans")

    created = json.loads(
        planner_tools.create_plan(
            "test",
            "Download articles",
            ["Download", "Verify"],
            ["All articles downloaded", "Success rate >= 75%"],
        )
    )["result"]
    plan_id = created["plan_id"]

    show_result = runner.invoke(app, ["plans", "show", plan_id, "--json"])
    assert show_result.exit_code == 0
    plan_data = json.loads(show_result.stdout)
    assert "success_conditions" in plan_data
    assert plan_data["success_conditions"] == [
        "All articles downloaded",
        "Success rate >= 75%",
    ]


def test_plans_remediate_preview_and_apply(tmp_path, monkeypatch):
    from agents.tools import planner as planner_tools

    monkeypatch.setattr(planner_tools, "_PLANS_DIR", tmp_path / ".plans")

    json.loads(
        planner_tools.create_plan(
            "test",
            "Download all empty articles",
            ["Download", "Verify"],
            ["No articles remain in empty status"],
        )
    )["result"]
    second = json.loads(
        planner_tools.create_plan(
            "test",
            "Download all empty articles now",
            ["Download", "Verify"],
            ["No articles remain in empty status"],
        )
    )["result"]

    # Force second to be a true duplicate by directly writing
    # its file as pending.
    second_plan = planner_tools._read_plan(second["plan_id"])
    second_plan["id"] = "duplicate-id"
    second_plan["status"] = "pending"
    planner_tools._write_plan(second_plan)

    preview = runner.invoke(app, ["plans", "remediate", "--json"])
    assert preview.exit_code == 0
    preview_data = json.loads(preview.stdout)
    assert preview_data["apply"] is False

    applied = runner.invoke(app, ["plans", "remediate", "--apply", "--json"])
    assert applied.exit_code == 0
    applied_data = json.loads(applied.stdout)
    assert applied_data["apply"] is True
