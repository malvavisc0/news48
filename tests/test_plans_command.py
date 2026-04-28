import json

from typer.testing import CliRunner

from news48.cli.main import app

runner = CliRunner()


def test_plans_list_show_cancel(planner_db, monkeypatch):
    from news48.core.agents.tools import planner as planner_tools

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
    assert any(item["plan_id"] == plan_id for item in json.loads(list_result.stdout))

    show_result = runner.invoke(app, ["plans", "show", plan_id, "--json"])
    assert show_result.exit_code == 0
    assert json.loads(show_result.stdout)["id"] == plan_id

    cancel_result = runner.invoke(app, ["plans", "cancel", plan_id, "--json"])
    assert cancel_result.exit_code == 0
    assert json.loads(cancel_result.stdout)["status"] == "failed"


def test_plans_show_displays_success_conditions(planner_db, monkeypatch):
    from news48.core.agents.tools import planner as planner_tools

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


def test_plans_show_json_includes_success_conditions(planner_db, monkeypatch):
    from news48.core.agents.tools import planner as planner_tools

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


def test_plans_remediate_preview_and_apply(planner_db, monkeypatch):
    from news48.core.agents.tools import planner as planner_tools

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


def test_plans_remediate_clears_campaign_parent_deadlock(planner_db, monkeypatch):
    """plans remediate --apply clears parent_id when parent is a pending
    campaign, preventing permanent deadlock (Fix 2)."""
    from news48.core.agents.tools import planner as planner_tools

    campaign = json.loads(
        planner_tools.create_plan(
            reason="test",
            task="Coordinate download backlog",
            steps=["Track coverage"],
            success_conditions=["Children exist"],
            plan_kind="campaign",
        )
    )["result"]

    child = json.loads(
        planner_tools.create_plan(
            reason="test",
            task="Download articles for example.com",
            steps=["Download", "Verify"],
            success_conditions=["Backlog reduced"],
            campaign_id=campaign["plan_id"],
        )
    )["result"]

    # Simulate the deadlock: set parent_id to the campaign
    child_plan = planner_tools._read_plan(child["plan_id"])
    child_plan["parent_id"] = campaign["plan_id"]
    planner_tools._write_plan(child_plan)

    result = runner.invoke(app, ["plans", "remediate", "--apply", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["apply"] is True

    # The normalization layer (_normalize_plan_for_consistency) runs first
    # inside _remediate_plan and catches the campaign-parent deadlock before
    # the explicit remediation rule.  Either action name is acceptable.
    child_changes = [c for c in data["changes"] if c["plan_id"] == child["plan_id"]]
    assert len(child_changes) >= 1
    actions = child_changes[0]["actions"]
    assert (
        "cleared_campaign_parent_deadlock" in actions
        or "normalized_status_mismatch" in actions
    ), f"Expected campaign deadlock fix action, got {actions}"

    # Verify on disk: parent_id cleared, campaign_id preserved
    fixed = planner_tools._read_plan(child["plan_id"])
    assert fixed["parent_id"] is None
    assert fixed["campaign_id"] == campaign["plan_id"]


def test_has_active_children_finds_parent_id_linked_children(planner_db, monkeypatch):
    """_has_active_children detects children linked via parent_id, not just
    campaign_id (Fix 4)."""
    from news48.cli.commands.plans import _has_active_children

    campaign_id = "test-campaign-id"
    all_plans = [
        {"id": campaign_id, "plan_kind": "campaign", "status": "pending"},
        {
            "id": "child-1",
            "parent_id": campaign_id,
            "status": "pending",
        },
    ]
    assert _has_active_children(campaign_id, all_plans) is True

    # Also test campaign_id-linked children
    all_plans_cid = [
        {"id": campaign_id, "plan_kind": "campaign", "status": "pending"},
        {
            "id": "child-2",
            "campaign_id": campaign_id,
            "status": "executing",
        },
    ]
    assert _has_active_children(campaign_id, all_plans_cid) is True

    # No children at all
    all_plans_empty = [
        {"id": campaign_id, "plan_kind": "campaign", "status": "pending"},
    ]
    assert _has_active_children(campaign_id, all_plans_empty) is False
