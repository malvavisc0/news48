import json

from news48.core import config
from news48.core.agents.tools import planner as planner_tools


def test_create_plan_defaults_to_pending_and_parent_id(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PLANS_DIR", tmp_path / ".plans")

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
    monkeypatch.setattr(config, "PLANS_DIR", tmp_path / ".plans")

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
    monkeypatch.setattr(config, "PLANS_DIR", tmp_path / ".plans")

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
    monkeypatch.setattr(config, "PLANS_DIR", tmp_path / ".plans")

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
    monkeypatch.setattr(config, "PLANS_DIR", tmp_path / ".plans")

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


def test_create_plan_rejects_blank_success_condition_entry(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PLANS_DIR", tmp_path / ".plans")

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


def test_create_plan_rejects_whitespace_success_condition_entry(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PLANS_DIR", tmp_path / ".plans")

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
    monkeypatch.setattr(config, "PLANS_DIR", tmp_path / ".plans")

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
    monkeypatch.setattr(config, "PLANS_DIR", tmp_path / ".plans")

    created = json.loads(
        planner_tools.create_plan("test", "Task", ["Step 1", "Verify"], ["Condition 1"])
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
    monkeypatch.setattr(config, "PLANS_DIR", tmp_path / ".plans")

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
    monkeypatch.setattr(config, "PLANS_DIR", tmp_path / ".plans")

    created = json.loads(
        planner_tools.create_plan("test", "Task", ["Step 1", "Verify"], ["Condition 1"])
    )["result"]
    json.loads(
        planner_tools.update_plan(
            reason="claim",
            plan_id=created["plan_id"],
            step_id="step-1",
            status="executing",
            plan_status="executing",
        )
    )

    data = json.loads(planner_tools.list_plans("test", status="executing"))
    assert len(data["result"]) == 1
    assert data["result"][0]["status"] == "executing"


def test_list_plans_filters_by_comma_separated_status(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PLANS_DIR", tmp_path / ".plans")

    # Create two plans
    plan_a = json.loads(
        planner_tools.create_plan("test", "Task A", ["Step 1"], ["Cond 1"])
    )["result"]
    json.loads(planner_tools.create_plan("test", "Fetch feeds", ["Step 1"], ["Cond 1"]))

    # Move plan_a to executing
    json.loads(
        planner_tools.update_plan(
            reason="claim",
            plan_id=plan_a["plan_id"],
            step_id="step-1",
            status="executing",
            plan_status="executing",
        )
    )

    # Filter by "pending,executing" should return both plans
    data = json.loads(planner_tools.list_plans("test", status="pending,executing"))
    statuses = {p["status"] for p in data["result"]}
    assert "pending" in statuses
    assert "executing" in statuses
    assert len(data["result"]) == 2

    # Filter by single status still works
    data = json.loads(planner_tools.list_plans("test", status="pending"))
    assert all(p["status"] == "pending" for p in data["result"])


def test_claim_plan_returns_no_eligible_plans_when_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PLANS_DIR", tmp_path / ".plans")

    payload = json.loads(planner_tools.claim_plan("test"))
    assert payload["error"] == ""
    result = payload["result"]
    assert isinstance(result, dict)
    assert result["status"] == "no_eligible_plans"
    assert "stop" in result["message"].lower()


def test_claim_plan_returns_empty_when_all_blocked(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PLANS_DIR", tmp_path / ".plans")

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
    assert payload["error"] == ""
    result = payload["result"]
    assert isinstance(result, dict)
    assert result["status"] == "no_eligible_plans"


def test_update_plan_rejects_invalid_plan_status(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PLANS_DIR", tmp_path / ".plans")

    created = json.loads(
        planner_tools.create_plan("test", "Task", ["Step 1", "Verify"], ["Condition 1"])
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


def test_update_plan_rejects_step_regression(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PLANS_DIR", tmp_path / ".plans")

    created = json.loads(
        planner_tools.create_plan("test", "Task", ["Step 1", "Verify"], ["Condition 1"])
    )["result"]

    json.loads(
        planner_tools.update_plan(
            reason="start",
            plan_id=created["plan_id"],
            step_id="step-1",
            status="executing",
            plan_status="executing",
        )
    )

    payload = json.loads(
        planner_tools.update_plan(
            reason="bad transition",
            plan_id=created["plan_id"],
            step_id="step-1",
            status="pending",
        )
    )

    assert payload["result"] == ""
    assert "Invalid step status transition" in payload["error"]


def test_update_plan_rejects_terminal_plan_mutation(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PLANS_DIR", tmp_path / ".plans")

    created = json.loads(
        planner_tools.create_plan("test", "Task", ["Step 1", "Verify"], ["Condition 1"])
    )["result"]

    json.loads(
        planner_tools.update_plan(
            reason="done",
            plan_id=created["plan_id"],
            step_id="step-1",
            status="completed",
            plan_status="completed",
        )
    )

    payload = json.loads(
        planner_tools.update_plan(
            reason="illegal mutate",
            plan_id=created["plan_id"],
            step_id="step-1",
            status="failed",
        )
    )

    assert payload["result"] != ""
    assert payload["error"] == ""
    assert "already terminal" in payload["warning"]


def test_create_plan_dedupes_active_same_family(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PLANS_DIR", tmp_path / ".plans")

    first = json.loads(
        planner_tools.create_plan(
            reason="test",
            task="Download all empty articles",
            steps=["Download", "Verify"],
            success_conditions=["No empty articles"],
        )
    )["result"]

    second = json.loads(
        planner_tools.create_plan(
            reason="test",
            task="Download all empty articles now",
            steps=["Download", "Verify"],
            success_conditions=["No empty articles"],
        )
    )["result"]

    assert second["plan_id"] == first["plan_id"]


def test_update_plan_rejects_terminal_plan_restatus_even_if_step_matches(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(config, "PLANS_DIR", tmp_path / ".plans")

    created = json.loads(
        planner_tools.create_plan(
            reason="test",
            task="Download empty articles",
            steps=["Download", "Verify"],
            success_conditions=["No empty articles"],
        )
    )["result"]

    json.loads(
        planner_tools.update_plan(
            reason="finish",
            plan_id=created["plan_id"],
            step_id="step-1",
            status="completed",
            plan_status="failed",
        )
    )

    payload = json.loads(
        planner_tools.update_plan(
            reason="duplicate finalization",
            plan_id=created["plan_id"],
            step_id="step-1",
            status="failed",
            plan_status="failed",
        )
    )

    assert payload["result"] != ""
    assert payload["error"] == ""
    assert "already terminal" in payload["warning"]


def test_create_plan_allows_multiple_feed_scoped_download_children(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(config, "PLANS_DIR", tmp_path / ".plans")

    campaign = json.loads(
        planner_tools.create_plan(
            reason="test",
            task="Coordinate download backlog for stale feeds",
            steps=["Track feed download coverage"],
            success_conditions=["Feed download child plans exist for target feeds"],
            plan_kind="campaign",
            scope_type="campaign",
            scope_value="download-backlog",
        )
    )["result"]

    feed_a = json.loads(
        planner_tools.create_plan(
            reason="test",
            task="Download empty articles for arstechnica.com",
            steps=[
                "Download arstechnica.com articles",
                "Verify arstechnica.com backlog is reduced",
            ],
            success_conditions=[
                "Eligible empty backlog for arstechnica.com is reduced"
            ],
            scope_type="feed",
            scope_value="arstechnica.com",
            campaign_id=campaign["plan_id"],
        )
    )["result"]

    feed_b = json.loads(
        planner_tools.create_plan(
            reason="test",
            task="Download empty articles for theverge.com",
            steps=[
                "Download theverge.com articles",
                "Verify theverge.com backlog is reduced",
            ],
            success_conditions=["Eligible empty backlog for theverge.com is reduced"],
            scope_type="feed",
            scope_value="theverge.com",
            campaign_id=campaign["plan_id"],
        )
    )["result"]

    assert campaign["plan_kind"] == "campaign"
    assert feed_a["plan_id"] != campaign["plan_id"]
    assert feed_b["plan_id"] != feed_a["plan_id"]
    assert feed_a["campaign_id"] == campaign["plan_id"]
    assert feed_b["campaign_id"] == campaign["plan_id"]


def test_create_plan_dedupes_same_feed_scoped_download_child(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PLANS_DIR", tmp_path / ".plans")

    first = json.loads(
        planner_tools.create_plan(
            reason="test",
            task="Download empty articles for arstechnica.com",
            steps=[
                "Download arstechnica.com articles",
                "Verify arstechnica.com backlog is reduced",
            ],
            success_conditions=[
                "Eligible empty backlog for arstechnica.com is reduced"
            ],
            scope_type="feed",
            scope_value="arstechnica.com",
        )
    )["result"]

    second = json.loads(
        planner_tools.create_plan(
            reason="test",
            task="Download empty articles for arstechnica.com now",
            steps=[
                "Download arstechnica.com articles",
                "Verify arstechnica.com backlog is reduced",
            ],
            success_conditions=[
                "Eligible empty backlog for arstechnica.com is reduced"
            ],
            scope_type="feed",
            scope_value="arstechnica.com",
        )
    )["result"]

    assert second["plan_id"] == first["plan_id"]


def test_claim_plan_skips_campaign_plans(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PLANS_DIR", tmp_path / ".plans")

    campaign = json.loads(
        planner_tools.create_plan(
            reason="test",
            task="Coordinate download backlog for stale feeds",
            steps=["Track feed download coverage"],
            success_conditions=["Feed download child plans exist for target feeds"],
            plan_kind="campaign",
            scope_type="campaign",
            scope_value="download-backlog",
        )
    )["result"]

    child = json.loads(
        planner_tools.create_plan(
            reason="test",
            task="Download empty articles for arstechnica.com",
            steps=[
                "Download arstechnica.com articles",
                "Verify arstechnica.com backlog is reduced",
            ],
            success_conditions=[
                "Eligible empty backlog for arstechnica.com is reduced"
            ],
            scope_type="feed",
            scope_value="arstechnica.com",
            campaign_id=campaign["plan_id"],
        )
    )["result"]

    claimed = json.loads(planner_tools.claim_plan("test"))["result"]
    assert claimed["plan_id"] == child["plan_id"]


def test_peek_next_plan_skips_campaign_plans(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PLANS_DIR", tmp_path / ".plans")

    campaign = json.loads(
        planner_tools.create_plan(
            reason="test",
            task="Coordinate download backlog for stale feeds",
            steps=["Track feed download coverage"],
            success_conditions=["Feed download child plans exist for target feeds"],
            plan_kind="campaign",
            scope_type="campaign",
            scope_value="download-backlog",
        )
    )["result"]

    child = json.loads(
        planner_tools.create_plan(
            reason="test",
            task="Download empty articles for arstechnica.com",
            steps=[
                "Download arstechnica.com articles",
                "Verify arstechnica.com backlog is reduced",
            ],
            success_conditions=[
                "Eligible empty backlog for arstechnica.com is reduced"
            ],
            scope_type="feed",
            scope_value="arstechnica.com",
            campaign_id=campaign["plan_id"],
        )
    )["result"]

    family = planner_tools.peek_next_plan()
    assert family == "download"
    assert child["plan_kind"] == "execution"


def test_create_plan_infers_download_parent_from_active_fetch(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PLANS_DIR", tmp_path / ".plans")

    fetch = json.loads(
        planner_tools.create_plan(
            reason="test",
            task="Fetch all feeds within last 120 minutes",
            steps=["Fetch", "Verify"],
            success_conditions=["All feeds are fresh"],
        )
    )["result"]

    download = json.loads(
        planner_tools.create_plan(
            reason="test",
            task="Download all empty articles",
            steps=["Download", "Verify"],
            success_conditions=["No empty articles"],
        )
    )["result"]

    assert download["parent_id"] == fetch["plan_id"]


def test_create_plan_infers_parse_parent_from_active_download(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PLANS_DIR", tmp_path / ".plans")

    download = json.loads(
        planner_tools.create_plan(
            reason="test",
            task="Download all empty articles",
            steps=["Download", "Verify"],
            success_conditions=["No empty articles"],
        )
    )["result"]

    parse = json.loads(
        planner_tools.create_plan(
            reason="test",
            task="Parse all downloaded articles",
            steps=["Parse", "Verify"],
            success_conditions=["No downloaded articles remain"],
        )
    )["result"]

    assert parse["parent_id"] == download["plan_id"]


def test_update_plan_accepts_step_description_alias(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PLANS_DIR", tmp_path / ".plans")

    created = json.loads(
        planner_tools.create_plan(
            reason="test",
            task="Download all empty articles",
            steps=["Run download", "verification-step"],
            success_conditions=["No empty articles"],
        )
    )["result"]

    payload = json.loads(
        planner_tools.update_plan(
            reason="verification by description",
            plan_id=created["plan_id"],
            step_id="verification-step",
            status="completed",
            result="Verification completed",
        )
    )

    assert payload["error"] == ""
    verification = next(
        s for s in payload["result"]["steps"] if s["description"] == "verification-step"
    )
    assert verification["status"] == "completed"


def test_claim_plan_sets_claim_owner_metadata(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PLANS_DIR", tmp_path / ".plans")

    created = json.loads(
        planner_tools.create_plan(
            reason="test",
            task="Fetch feeds",
            steps=["Fetch", "Verify"],
            success_conditions=["All feeds fetched"],
        )
    )["result"]

    claimed = json.loads(planner_tools.claim_plan("test"))["result"]
    assert claimed["plan_id"] == created["plan_id"]

    raw = planner_tools._read_plan(created["plan_id"])
    assert raw["claimed_by"].startswith("pid:")
    assert raw["claimed_at"] is not None


def test_stale_detects_dead_claimed_pid(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PLANS_DIR", tmp_path / ".plans")

    created = json.loads(
        planner_tools.create_plan(
            reason="test",
            task="Download articles",
            steps=["Download", "Verify"],
            success_conditions=["No empty articles"],
        )
    )["result"]

    plan = planner_tools._read_plan(created["plan_id"])
    plan["status"] = "executing"
    plan["claimed_by"] = "pid:999999"
    planner_tools._write_plan(plan)

    monkeypatch.setattr(planner_tools._lifecycle, "_is_pid_alive", lambda _pid: False)

    payload = json.loads(planner_tools.recover_stale_plans("startup recovery"))
    assert payload["error"] == ""
    assert payload["result"]["requeued"] == 1

    recovered = planner_tools._read_plan(created["plan_id"])
    assert recovered["status"] == "pending"
    assert recovered["claimed_by"] is None
    assert recovered["claimed_at"] is None


# --- Auto-recovery fixes: _is_plan_stale, _normalize, _read_plan ---


def test_is_plan_stale_returns_true_when_claimed_by_is_none(tmp_path, monkeypatch):
    """An executing plan with no claimed_by is immediately stale because
    ownership cannot be verified."""
    monkeypatch.setattr(config, "PLANS_DIR", tmp_path / ".plans")

    created = json.loads(
        planner_tools.create_plan(
            "test", "Download articles", ["Step 1"], ["No empty articles"]
        )
    )["result"]

    plan = planner_tools._read_plan(created["plan_id"])
    plan["status"] = "executing"
    plan["claimed_by"] = None
    plan["claimed_at"] = None
    planner_tools._write_plan(plan)

    assert planner_tools._is_plan_stale(plan) is True


def test_is_plan_stale_returns_true_when_claimed_by_is_missing(tmp_path, monkeypatch):
    """An executing plan whose JSON has no claimed_by key at all is stale."""
    monkeypatch.setattr(config, "PLANS_DIR", tmp_path / ".plans")

    created = json.loads(
        planner_tools.create_plan(
            "test", "Download articles", ["Step 1"], ["No empty articles"]
        )
    )["result"]

    plan = planner_tools._read_plan(created["plan_id"])
    plan["status"] = "executing"
    plan.pop("claimed_by", None)
    plan.pop("claimed_at", None)
    planner_tools._write_plan(plan)

    assert planner_tools._is_plan_stale(plan) is True


def test_is_plan_stale_returns_false_when_pid_alive(tmp_path, monkeypatch):
    """An executing plan claimed by a live PID is NOT stale."""
    monkeypatch.setattr(config, "PLANS_DIR", tmp_path / ".plans")

    created = json.loads(
        planner_tools.create_plan(
            "test", "Download articles", ["Step 1"], ["No empty articles"]
        )
    )["result"]

    plan = planner_tools._read_plan(created["plan_id"])
    plan["status"] = "executing"
    plan["claimed_by"] = "pid:12345"
    planner_tools._write_plan(plan)

    monkeypatch.setattr(planner_tools._lifecycle, "_is_pid_alive", lambda _pid: True)
    assert planner_tools._is_plan_stale(plan) is False


def test_normalize_resets_orphaned_executing_plan_to_pending(tmp_path, monkeypatch):
    """An executing plan with no claimed_by is reset to pending with
    executing steps reverted to pending."""
    monkeypatch.setattr(config, "PLANS_DIR", tmp_path / ".plans")

    created = json.loads(
        planner_tools.create_plan(
            "test",
            "Download articles",
            ["Step 1", "Step 2"],
            ["No empty articles"],
        )
    )["result"]

    plan = planner_tools._read_plan(created["plan_id"])
    plan["status"] = "executing"
    plan["claimed_by"] = None
    plan["steps"][0]["status"] = "executing"
    planner_tools._write_plan(plan)

    changed = planner_tools._normalize_plan_for_consistency(plan)

    assert changed is True
    assert plan["status"] == "pending"
    assert plan["steps"][0]["status"] == "pending"
    assert plan["steps"][1]["status"] == "pending"


def test_normalize_does_not_touch_executing_plan_with_claimed_by(tmp_path, monkeypatch):
    """An executing plan WITH a claimed_by PID is not reset by normalize."""
    monkeypatch.setattr(config, "PLANS_DIR", tmp_path / ".plans")

    created = json.loads(
        planner_tools.create_plan(
            "test", "Download articles", ["Step 1"], ["No empty articles"]
        )
    )["result"]

    plan = planner_tools._read_plan(created["plan_id"])
    plan["status"] = "executing"
    plan["claimed_by"] = "pid:12345"
    plan["steps"][0]["status"] = "executing"
    planner_tools._write_plan(plan)

    changed = planner_tools._normalize_plan_for_consistency(plan)

    assert changed is False
    assert plan["status"] == "executing"
    assert plan["steps"][0]["status"] == "executing"


def test_read_plan_backfills_missing_schema_fields(tmp_path, monkeypatch):
    """Plans created before claimed_by/requeue_count schema additions
    get sane defaults on read."""
    monkeypatch.setattr(config, "PLANS_DIR", tmp_path / ".plans")

    created = json.loads(
        planner_tools.create_plan(
            "test", "Download articles", ["Step 1"], ["No empty articles"]
        )
    )["result"]

    # Simulate old-schema plan by stripping new fields from JSON on disk
    path = planner_tools._plan_path(created["plan_id"])
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw.pop("claimed_by", None)
    raw.pop("claimed_at", None)
    raw.pop("requeue_count", None)
    raw.pop("requeued_at", None)
    raw.pop("requeue_reason", None)
    path.write_text(json.dumps(raw, indent=2), encoding="utf-8")

    plan = planner_tools._read_plan(created["plan_id"])
    assert plan["claimed_by"] is None
    assert plan["claimed_at"] is None
    assert plan["requeue_count"] == 0
    assert plan["requeued_at"] is None
    assert plan["requeue_reason"] is None


def test_claim_plan_recovers_orphaned_executing_plan(tmp_path, monkeypatch):
    """claim_plan requeues an executing plan with no claimed_by and then
    claims it in the same call."""
    monkeypatch.setattr(config, "PLANS_DIR", tmp_path / ".plans")

    created = json.loads(
        planner_tools.create_plan(
            "test",
            "Download articles",
            ["Step 1", "Step 2"],
            ["No empty articles"],
        )
    )["result"]

    # Simulate orphaned plan: executing, no claimed_by, executing step
    plan = planner_tools._read_plan(created["plan_id"])
    plan["status"] = "executing"
    plan["claimed_by"] = None
    plan["claimed_at"] = None
    plan["steps"][0]["status"] = "completed"
    plan["steps"][1]["status"] = "executing"
    planner_tools._write_plan(plan)

    # claim_plan should detect the orphan, requeue it, then claim it
    payload = json.loads(planner_tools.claim_plan("auto-recovery"))
    assert payload["error"] == ""
    assert payload["result"] != ""
    assert payload["result"]["plan_id"] == created["plan_id"]
    assert payload["result"]["status"] == "executing"

    # The on-disk plan should now have a valid claimed_by
    disk = planner_tools._read_plan(created["plan_id"])
    assert disk["claimed_by"] is not None
    assert disk["claimed_by"].startswith("pid:")


def test_recover_stale_plans_normalizes_orphaned_plan(tmp_path, monkeypatch):
    """recover_stale_plans normalizes an orphaned executing plan (no
    claimed_by) back to pending via _normalize_plan_for_consistency,
    which runs before the stale-requeue check."""
    monkeypatch.setattr(config, "PLANS_DIR", tmp_path / ".plans")

    created = json.loads(
        planner_tools.create_plan(
            "test", "Download articles", ["Step 1"], ["No empty articles"]
        )
    )["result"]

    plan = planner_tools._read_plan(created["plan_id"])
    plan["status"] = "executing"
    plan["claimed_by"] = None
    plan["steps"][0]["status"] = "executing"
    planner_tools._write_plan(plan)

    payload = json.loads(planner_tools.recover_stale_plans("startup recovery"))
    assert payload["error"] == ""
    # Normalization catches the orphan before the stale-requeue path
    assert payload["result"]["normalized"] >= 1

    recovered = planner_tools._read_plan(created["plan_id"])
    assert recovered["status"] == "pending"
    assert recovered["steps"][0]["status"] == "pending"


# ------------------------------------------------------------------
# Campaign-parent deadlock fix tests
# ------------------------------------------------------------------


def test_claim_plan_allows_child_of_campaign_parent(tmp_path, monkeypatch):
    """claim_plan claims a child whose parent_id points to a pending campaign.

    This is the core deadlock fix: campaign parents are non-blocking.
    """
    monkeypatch.setattr(config, "PLANS_DIR", tmp_path / ".plans")

    campaign = json.loads(
        planner_tools.create_plan(
            reason="test",
            task="Coordinate download backlog for stale feeds",
            steps=["Track feed download coverage"],
            success_conditions=["Feed download child plans exist"],
            plan_kind="campaign",
            scope_type="campaign",
            scope_value="download-backlog",
        )
    )["result"]

    # Create child using campaign_id (correct usage)
    child = json.loads(
        planner_tools.create_plan(
            reason="test",
            task="Download empty articles for example.com",
            steps=["Download articles", "Verify backlog reduced"],
            success_conditions=["Backlog for example.com is reduced"],
            scope_type="feed",
            scope_value="example.com",
            campaign_id=campaign["plan_id"],
        )
    )["result"]

    # Now manually set parent_id to the campaign (simulating the deadlock)
    child_plan = planner_tools._read_plan(child["plan_id"])
    child_plan["parent_id"] = campaign["plan_id"]
    planner_tools._write_plan(child_plan)

    # claim_plan should still claim the child because campaign parents
    # are non-blocking
    claimed = json.loads(planner_tools.claim_plan("deadlock test"))["result"]
    assert claimed["plan_id"] == child["plan_id"]
    assert claimed["status"] == "executing"


def test_create_plan_converts_campaign_parent_id_to_campaign_id(tmp_path, monkeypatch):
    """create_plan converts parent_id pointing at a campaign to campaign_id.

    This prevents deadlocks at creation time (Fix 5).
    """
    monkeypatch.setattr(config, "PLANS_DIR", tmp_path / ".plans")

    campaign = json.loads(
        planner_tools.create_plan(
            reason="test",
            task="Coordinate download backlog",
            steps=["Track coverage"],
            success_conditions=["Children exist"],
            plan_kind="campaign",
        )
    )["result"]

    # Create child incorrectly using parent_id pointing at campaign
    child = json.loads(
        planner_tools.create_plan(
            reason="test",
            task="Download empty articles for example.com",
            steps=["Download", "Verify"],
            success_conditions=["Backlog reduced"],
            parent_id=campaign["plan_id"],
        )
    )["result"]

    # parent_id should have been converted to campaign_id
    child_plan = planner_tools._read_plan(child["plan_id"])
    assert (
        child_plan["parent_id"] is None
    ), "parent_id should be cleared when parent is a campaign"
    assert (
        child_plan["campaign_id"] == campaign["plan_id"]
    ), "campaign_id should be set to the campaign's plan_id"


def test_normalize_converts_campaign_parent_to_campaign_id(tmp_path, monkeypatch):
    """_normalize_plan_for_consistency converts parent_id pointing at a
    campaign to a non-blocking campaign_id (Fix 6)."""
    monkeypatch.setattr(config, "PLANS_DIR", tmp_path / ".plans")

    # Create campaign
    campaign = json.loads(
        planner_tools.create_plan(
            reason="test",
            task="Coordinate download backlog",
            steps=["Track coverage"],
            success_conditions=["Children exist"],
            plan_kind="campaign",
        )
    )["result"]

    # Create child plan then manually set parent_id to campaign
    child = json.loads(
        planner_tools.create_plan(
            reason="test",
            task="Download articles for example.com",
            steps=["Download", "Verify"],
            success_conditions=["Backlog reduced"],
        )
    )["result"]

    child_plan = planner_tools._read_plan(child["plan_id"])
    child_plan["parent_id"] = campaign["plan_id"]
    child_plan["campaign_id"] = None
    planner_tools._write_plan(child_plan)

    changed = planner_tools._normalize_plan_for_consistency(child_plan)

    assert changed is True
    assert child_plan["parent_id"] is None
    assert child_plan["campaign_id"] == campaign["plan_id"]


def test_normalize_clears_orphaned_non_uuid_parent_id(tmp_path, monkeypatch):
    """_normalize_plan_for_consistency clears orphaned non-UUID parent_id
    references like 'parsing-campaign-20260413-new' (Fix 6)."""
    monkeypatch.setattr(config, "PLANS_DIR", tmp_path / ".plans")

    created = json.loads(
        planner_tools.create_plan(
            reason="test",
            task="Parse articles batch",
            steps=["Parse", "Verify"],
            success_conditions=["All parsed"],
        )
    )["result"]

    plan = planner_tools._read_plan(created["plan_id"])
    plan["parent_id"] = "parsing-campaign-20260413-new"  # Not a UUID
    planner_tools._write_plan(plan)

    changed = planner_tools._normalize_plan_for_consistency(plan)

    assert changed is True
    assert plan["parent_id"] is None


def test_auto_complete_campaigns_marks_completed(tmp_path, monkeypatch):
    """_auto_complete_campaigns marks a campaign as completed when all
    children are completed (Fix 3)."""
    monkeypatch.setattr(config, "PLANS_DIR", tmp_path / ".plans")

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

    # Mark child as completed
    child_plan = planner_tools._read_plan(child["plan_id"])
    child_plan["status"] = "completed"
    for step in child_plan["steps"]:
        step["status"] = "completed"
    planner_tools._write_plan(child_plan)

    completed = planner_tools._auto_complete_campaigns()

    assert completed == 1
    campaign_plan = planner_tools._read_plan(campaign["plan_id"])
    assert campaign_plan["status"] == "completed"


def test_auto_complete_campaigns_marks_failed_when_child_failed(tmp_path, monkeypatch):
    """_auto_complete_campaigns marks a campaign as failed when any child
    is failed and all children are terminal."""
    monkeypatch.setattr(config, "PLANS_DIR", tmp_path / ".plans")

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

    # Mark child as failed
    child_plan = planner_tools._read_plan(child["plan_id"])
    child_plan["status"] = "failed"
    for step in child_plan["steps"]:
        step["status"] = "failed"
    planner_tools._write_plan(child_plan)

    completed = planner_tools._auto_complete_campaigns()

    assert completed == 1
    campaign_plan = planner_tools._read_plan(campaign["plan_id"])
    assert campaign_plan["status"] == "failed"
