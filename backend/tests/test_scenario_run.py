"""`POST /scenarios/{id}/run` — the link is written by the INSERT.

WHY THIS FILE EXISTS. That endpoint had never worked. It assigned
`run.scenario_id` after `SimulationRunService.create()` had already committed,
then committed again — and `set_rls_context` uses `SET LOCAL`, which Postgres
discards at COMMIT. By the second commit the session had no identity, the
`simulation_runs` row-level-security policy matched zero rows, and SQLAlchemy
raised `StaleDataError: expected to update 1 row(s); 0 were matched`. The route
returned 500, the background task was never scheduled, and the run stayed
`queued` for ever.

Nobody noticed because the `scenarios` table was empty: there was no UI to
create one, so the endpoint had never been called in anger. It was found by
building that UI and pressing the button.

WHAT THESE TESTS CAN AND CANNOT DO. The test database is built from ORM metadata
via `create_all`, so **the RLS policies do not exist in it** — an UPDATE that
production refuses succeeds here. That is the same blind spot LIMITATIONS.md 1c
records for the alerts bug. So the runtime failure is not reproducible in this
harness, and these tests guard it at the source level instead: the link must be
set in the INSERT, and the route must not commit a second time.
"""
import inspect
import uuid

import pytest

from app.api.v1 import scenarios as scen
from app.services.simulation_run import SimulationRunService


def test_create_accepts_scenario_id():
    """The link belongs to the INSERT, not to a follow-up UPDATE."""
    sig = inspect.signature(SimulationRunService.create)
    assert "scenario_id" in sig.parameters, (
        "SimulationRunService.create must take scenario_id so the link is "
        "written in the same statement as the row.")


def test_create_sets_scenario_id_on_the_model():
    src = inspect.getsource(SimulationRunService.create)
    assert "scenario_id=scenario_id" in src, (
        "scenario_id must be passed to the SimulationRun constructor")


def test_run_scenario_does_not_write_twice():
    """The regression itself, guarded at the source.

    A second `db.commit()` in this route is the bug returning: after the first
    commit the session is anonymous to every RLS policy, so any write that
    follows silently matches nothing.
    """
    src = inspect.getsource(scen.run_scenario)
    assert "run.scenario_id = " not in src, (
        "assigning scenario_id after create() re-introduces the "
        "commit-then-update failure")
    assert src.count("db.commit()") == 0, (
        "run_scenario must not commit after SimulationRunService.create — the "
        "RLS context is gone by then")


def test_run_scenario_passes_the_link_through():
    src = inspect.getsource(scen.run_scenario)
    assert "scenario_id=sc.id" in src


@pytest.mark.asyncio
async def test_run_scenario_links_the_run(client, admin_token, db_session):
    """End to end in the harness: a scenario run comes back 202 with a run id,
    and the stored run carries the scenario link."""
    from sqlalchemy import select
    from app.models.isr_point import IsrPoint
    from app.models.simulation_run import SimulationRun

    site = IsrPoint(name=f"scenario-test-{uuid.uuid4().hex[:6]}",
                    injection_rate_m3_day=1000.0)
    db_session.add(site)
    await db_session.commit()

    h = {"Authorization": f"Bearer {admin_token}"}
    r = await client.post("/api/v1/scenarios", headers=h, json={
        "name": "linked", "isr_point_id": str(site.id),
        "params": {"species": "uranium_ppb", "time_years": 10},
    })
    assert r.status_code == 201, r.text
    sid = r.json()["id"]

    r = await client.post(f"/api/v1/scenarios/{sid}/run", headers=h)
    assert r.status_code == 202, r.text
    run_id = r.json()["run_id"]

    row = (await db_session.execute(
        select(SimulationRun).where(SimulationRun.id == uuid.UUID(run_id)))
    ).scalar_one()
    assert str(row.scenario_id) == sid, (
        "the run was created but not linked to its scenario")
