import json

from agents.tools import planner as planner_tools


def test_create_plan_defaults_to_pending_and_parent_id(tmp_path, monkeypatch):
    monkeypatch.setattr(planner_tools, "_PLANS_DIR", tmp_path / ".plans")

    payload = json.loads(
        planner_tools.create_plan(
            reason="test",
            task="Download articles",
            steps=["Step 1", "Verify"],
            success_conditions=["All articles downloaded", "No errors"],
            parent_id="parent-123",
        )
    )

    result = payload["result"]
    assert result["status"] == "pending"
    assert result["parent_id"] == "parent-123"
    assert result["success_conditions"] == [
        "All articles downloaded",
        "No errors",
    ]


def test_create_plan_stores_success_conditions(tmp_path, monkeypatch):
    monkeypatch.setattr(planner_tools, "_PLANS_DIR", tmp_path / ".plans")

    payload = json.loads(
        planner_tools.create_plan(
            reason="test",
            task="Fetch all feeds",
            steps=["Fetch", "Verify"],
            success_conditions=[
                "All 55 feeds have been fetched",
                "Fetch error rate below 5%",
            ],
        )
    )

    result = payload["result"]
    assert result["success_conditions"] == [
        "All 55 feeds have been fetched",
        "Fetch error rate below 5%",
    ]


def test_create_plan_rejects_empty_task(tmp_path, monkeypatch):
    monkeypatch.setattr(planner_tools, "_PLANS_DIR", tmp_path / ".plans")

    payload = json.loads(
        planner_tools.create_plan(
            reason="test",
            task="",
            steps=["Step 1"],
            success_conditions=["Condition 1"],
        )
    )

    assert payload["result"] == ""
    assert "task is required" in payload["error"]


def test_create_plan_rejects_whitespace_only_task(tmp_path, monkeypatch):
    monkeypatch.setattr(planner_tools, "_PLANS_DIR", tmp_path / ".plans")

    payload = json.loads(
        planner_tools.create_plan(
            reason="test",
            task="   ",
            steps=["Step 1"],
            success_conditions=["Condition 1"],
        )
    )

    assert payload["result"] == ""
    assert "task is required" in payload["error"]


def test_create_plan_rejects_empty_success_conditions(tmp_path, monkeypatch):
    monkeypatch.setattr(planner_tools, "_PLANS_DIR", tmp_path / ".plans")

    payload = json.loads(
        planner_tools.create_plan(
            reason="test",
            task="Valid task",
            steps=["Step 1"],
            success_conditions=[],
        )
    )

    assert payload["result"] == ""
    assert "success_conditions is required" in payload["error"]


def test_create_plan_rejects_blank_success_condition_entry(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(planner_tools, "_PLANS_DIR", tmp_path / ".plans")

    payload = json.loads(
        planner_tools.create_plan(
            reason="test",
            task="Valid task",
            steps=["Step 1"],
            success_conditions=["Valid condition", ""],
        )
    )

    assert payload["result"] == ""
    assert "cannot be blank" in payload["error"]


def test_create_plan_rejects_whitespace_success_condition_entry(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(planner_tools, "_PLANS_DIR", tmp_path / ".plans")

    payload = json.loads(
        planner_tools.create_plan(
            reason="test",
            task="Valid task",
            steps=["Step 1"],
            success_conditions=["Valid condition", "   "],
        )
    )

    assert payload["result"] == ""
    assert "cannot be blank" in payload["error"]


def test_serialize_plan_includes_success_conditions(tmp_path, monkeypatch):
    monkeypatch.setattr(planner_tools, "_PLANS_DIR", tmp_path / ".plans")

    payload = json.loads(
        planner_tools.create_plan(
            reason="test",
            task="Test task",
            steps=["Step 1"],
            success_conditions=["Condition A", "Condition B"],
        )
    )

    result = payload["result"]
    assert "success_conditions" in result
    assert result["success_conditions"] == ["Condition A", "Condition B"]


def test_update_plan_accepts_explicit_plan_status(tmp_path, monkeypatch):
    monkeypatch.setattr(planner_tools, "_PLANS_DIR", tmp_path / ".plans")

    created = json.loads(
        planner_tools.create_plan(
            "test", "Task", ["Step 1", "Verify"], ["Condition 1"]
        )
    )["result"]

    updated = json.loads(
        planner_tools.update_plan(
            reason="claim",
            plan_id=created["plan_id"],
            step_id="step-1",
            status="completed",
            plan_status="executing",
        )
    )["result"]

    assert updated["status"] == "executing"


def test_claim_plan_respects_parent_dependency(tmp_path, monkeypatch):
    monkeypatch.setattr(planner_tools, "_PLANS_DIR", tmp_path / ".plans")

    parent = json.loads(
        planner_tools.create_plan(
            "test", "Fetch", ["Fetch", "Verify"], ["All feeds fetched"]
        )
    )["result"]
    child = json.loads(
        planner_tools.create_plan(
            "test",
            "Download",
            ["Download", "Verify"],
            ["All articles downloaded"],
            parent_id=parent["plan_id"],
        )
    )["result"]

    claimed = json.loads(planner_tools.claim_plan("test"))["result"]
    assert claimed["plan_id"] == parent["plan_id"]

    json.loads(
        planner_tools.update_plan(
            reason="done",
            plan_id=parent["plan_id"],
            step_id="step-1",
            status="completed",
            plan_status="completed",
        )
    )

    claimed_child = json.loads(planner_tools.claim_plan("test"))["result"]
    assert claimed_child["plan_id"] == child["plan_id"]


def test_list_plans_filters_by_status(tmp_path, monkeypatch):
    monkeypatch.setattr(planner_tools, "_PLANS_DIR", tmp_path / ".plans")

    created = json.loads(
        planner_tools.create_plan(
            "test", "Task", ["Step 1", "Verify"], ["Condition 1"]
        )
    )["result"]
    json.loads(
        planner_tools.update_plan(
            reason="claim",
            plan_id=created["plan_id"],
            step_id="step-1",
            status="in_progress",
            plan_status="executing",
        )
    )

    data = json.loads(planner_tools.list_plans("test", status="executing"))
    assert len(data["result"]) == 1
    assert data["result"][0]["status"] == "executing"


def test_claim_plan_returns_empty_when_no_plans(tmp_path, monkeypatch):
    monkeypatch.setattr(planner_tools, "_PLANS_DIR", tmp_path / ".plans")

    payload = json.loads(planner_tools.claim_plan("test"))
    assert payload["result"] == ""
    assert payload["error"] == ""


def test_claim_plan_returns_empty_when_all_blocked(tmp_path, monkeypatch):
    monkeypatch.setattr(planner_tools, "_PLANS_DIR", tmp_path / ".plans")

    parent = json.loads(
        planner_tools.create_plan(
            "test", "Fetch", ["Fetch", "Verify"], ["All feeds fetched"]
        )
    )["result"]
    # Child depends on parent, but parent is still pending
    json.loads(
        planner_tools.create_plan(
            "test",
            "Download",
            ["Download", "Verify"],
            ["All articles downloaded"],
            parent_id=parent["plan_id"],
        )
    )

    # Claim the parent (only eligible plan)
    json.loads(planner_tools.claim_plan("test"))

    # Now parent is executing, child is blocked -- nothing eligible
    payload = json.loads(planner_tools.claim_plan("test"))
    assert payload["result"] == ""
    assert payload["error"] == ""


def test_update_plan_rejects_invalid_plan_status(tmp_path, monkeypatch):
    monkeypatch.setattr(planner_tools, "_PLANS_DIR", tmp_path / ".plans")

    created = json.loads(
        planner_tools.create_plan(
            "test", "Task", ["Step 1", "Verify"], ["Condition 1"]
        )
    )["result"]

    payload = json.loads(
        planner_tools.update_plan(
            reason="bad status",
            plan_id=created["plan_id"],
            step_id="step-1",
            status="completed",
            plan_status="invalid_status",
        )
    )

    assert payload["result"] == ""
    assert "Invalid plan_status" in payload["error"]
