"""Put one complete, honest story into the database.

THE PROBLEM THIS SOLVES. A fresh or lightly-used deployment has every feature
and no evidence of any of them: Publications reads "Published (0)", the
Alerts inbox is empty, the citizen map shows no assessment, and the map is
decorated with sites named "Isr1", "Try1" and "try2" that somebody made while
clicking around. Every empty state is technically correct and every one of
them makes the product look unfinished to a first-time viewer.

WHAT IT DOES, in order, each step idempotent:

  1. Removes the throwaway sites named on the command line, refusing any that
     has a published advisory behind it (a public statement is not junk).
  2. Gives the named demonstration site an injection start date if it has
     none. The breach-due alert cannot count from a missing date.
  3. If that site has no PUBLISHED screening: creates a run, executes the
     engine inline, proposes and publishes an advisory as the single admin
     account -- loaded from the database by role, never by password -- so the
     alerts that publication raises are raised, and delivered.
  4. Runs the measured-exceedance scan, so the wells that are over a health
     limit today produce their alerts, and delivers those too.
  5. Gives the demonstration citizen a home block -- the block under the
     demonstration site -- and follows it, so their inbox holds the alert.
  6. Prints what the database now holds.

It uses the SERVICE LAYER, not raw inserts, so every row it creates is one the
product could have created itself: the run is pinned to a model card, the
advisory has a decider, the alerts went through the same idempotent inserts,
and the audit log records each act.

Run from `backend/` under the profile that points at the database you mean:

    python -m scripts.seed_demo_story

Options:
    --site NAME        the site to publish for (default: Jaduguda (hypothetical ISR))
    --remove NAME ...  throwaway sites to delete (default: Isr1 Try1 try2 try3 isr1 try1)
    --start YYYY-MM-DD hypothetical injection start if the site has none (default 2010-01-01)
    --citizen EMAIL    the demo citizen to give a home block (default citizen@jaldrishti.local)
    --dry-run          report what would happen and change nothing
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime, timezone

from loguru import logger
from sqlalchemy import select, text

from app.database import AsyncSessionLocal, set_rls_context
from app.models.advisory import Advisory
from app.models.isr_point import IsrPoint
from app.models.user import User, UserRole


DEFAULT_REMOVE = ["Isr1", "Try1", "try2", "try3", "isr1", "try1"]
DEFAULT_SITE = "Jaduguda (hypothetical ISR)"
DEFAULT_CITIZEN = "citizen@jaldrishti.local"

HEADLINE = "Groundwater screening published for the Jaduguda area"
WHAT_IT_MEANS = (
    "A hypothetical uranium in-situ recovery operation was modelled at a "
    "location near Jaduguda in East Singhbhum. The model estimates how far "
    "dissolved uranium would travel through the fractured rock over ten years "
    "of operation, how much of the surrounding area it would affect, and "
    "whether it could reach the shallow groundwater that supplies wells and "
    "handpumps. No such mine exists or is planned; this is a preparedness "
    "screening so that, if one were ever proposed, the people living over "
    "this aquifer would already know what the model expects."
)
WHAT_TO_DO = (
    "Nothing needs to change today. If you draw water from a borewell or "
    "handpump in the blocks named here, ask your block water office when it "
    "was last tested for uranium and nitrate -- that measurement, not this "
    "model, is what tells you about your water."
)


def _quiet_sql() -> None:
    """The development engine echoes every statement; this script's output is
    the summary, not the SQL."""
    from app.database import engine
    engine.echo = False


async def _admin(db) -> User:
    admin = (await db.execute(
        select(User).where(User.role == UserRole.admin))).scalars().first()
    if admin is None:
        sys.exit("No admin account exists. Run `python -m scripts.bootstrap_admin` first.")
    return admin


async def _site(db, name: str) -> IsrPoint:
    site = (await db.execute(
        select(IsrPoint).where(IsrPoint.name == name))).scalars().first()
    if site is None:
        sys.exit(f"No site named {name!r}. Sites present: "
                 + ", ".join(r[0] for r in (await db.execute(
                     text("SELECT name FROM isr_points ORDER BY name"))).all()))
    return site


async def step_remove(db, names: list[str], dry: bool) -> None:
    lowered = [n.lower() for n in names]
    rows = (await db.execute(text("""
        SELECT p.id::text, p.name,
               (SELECT count(*) FROM advisories a
                 WHERE a.isr_point_id = p.id AND a.status = 'published') AS published
        FROM isr_points p WHERE lower(p.name) = ANY(:names)
    """), {"names": lowered})).all()
    for pid, name, published in rows:
        if published:
            logger.warning(f"keeping {name!r}: it has {published} published advisory(ies)")
            continue
        logger.info(f"{'would delete' if dry else 'deleting'} throwaway site {name!r}")
        if not dry:
            # RESTRICT on advisories.run_id: withdraw/reject rows must go first.
            await db.execute(text("DELETE FROM advisories WHERE isr_point_id = :p"), {"p": pid})
            await db.execute(text("DELETE FROM isr_points WHERE id = :p"), {"p": pid})
    if not dry:
        await db.commit()
        await set_rls_context(db, bypass=True)


async def step_start_date(db, site: IsrPoint, start: str, dry: bool) -> None:
    if site.injection_start_date is not None:
        logger.info(f"{site.name}: injection start already {site.injection_start_date:%Y-%m-%d}")
        return
    logger.info(f"{site.name}: {'would set' if dry else 'setting'} injection start {start}")
    if not dry:
        site.injection_start_date = datetime.fromisoformat(start).replace(tzinfo=timezone.utc)
        await db.commit()
        await set_rls_context(db, bypass=True)


async def step_publish(db, site: IsrPoint, admin: User, dry: bool) -> None:
    from app.api.v1.simulations import _run_in_background
    from app.services.advisory import AdvisoryService
    from app.services.simulation_run import SimulationRunService

    existing = (await db.execute(
        select(Advisory).where(Advisory.isr_point_id == site.id,
                               Advisory.status == "published"))).scalars().first()
    if existing is not None:
        logger.info(f"{site.name}: already has a published screening ({existing.id})")
        return
    if dry:
        logger.info(f"{site.name}: would run the engine, propose and publish as {admin.email}")
        return

    svc = SimulationRunService(db, system=True)
    run = await svc.create(actor=admin, isr_id=site.id,
                           params={"species": "uranium_ppb", "time_years": 10.0},
                           ip=None)
    await set_rls_context(db, bypass=True)
    logger.info(f"run {run.id} created; executing the engine inline ...")
    await _run_in_background(run.id)
    await set_rls_context(db, bypass=True)
    await db.refresh(run)
    if run.status != "completed":
        sys.exit(f"run {run.id} ended '{run.status}': {run.error_message}")
    logger.info(f"run {run.id} completed")

    adv = await AdvisoryService(db).propose(
        actor=admin, run_id=run.id, headline=HEADLINE,
        what_it_means=WHAT_IT_MEANS, what_to_do=WHAT_TO_DO, ip=None)
    await set_rls_context(db, bypass=True)
    adv = await AdvisoryService(db).decide(
        actor=admin, advisory_id=adv.id, decision="publish",
        note="Published by the demonstration seed so the public record is not empty.",
        ip=None)
    await set_rls_context(db, bypass=True)
    logger.info(f"advisory {adv.id} published; blocks: "
                + ", ".join(b.get("name", "?") for b in (adv.affected_blocks or [])))


async def step_scan(dry: bool) -> None:
    from app.services.alerts import AlertService
    from app.services.notify import deliver_pending
    if dry:
        logger.info("would run the measured-exceedance scan and deliver")
        return
    async with AsyncSessionLocal() as db:
        await set_rls_context(db, bypass=True)
        out = await AlertService(db).scan_measured_exceedances()
    logger.info(f"measured scan: {out['wells_over_limit']} well(s) over a limit, "
                f"{out['alerts_created']} new alert(s)")
    d = await deliver_pending()
    logger.info(f"delivery: {d}")


async def step_citizen(db, site: IsrPoint, email: str, dry: bool) -> None:
    cit = (await db.execute(select(User).where(User.email == email))).scalars().first()
    if cit is None:
        logger.warning(f"no account {email!r}; skipping the citizen step")
        return
    block = (await db.execute(text("""
        SELECT b.id::text, b.name, d.name AS district
        FROM blocks b LEFT JOIN districts d ON d.id = b.district_id
        JOIN isr_points p ON p.id = :pid
        WHERE b.geometry IS NOT NULL AND ST_Contains(b.geometry, p.location)
        LIMIT 1
    """), {"pid": str(site.id)})).first()
    if block is None:
        logger.warning(f"{site.name} is not inside any block polygon; citizen step skipped")
        return
    logger.info(f"{email}: {'would set' if dry else 'setting'} home block "
                f"{block[1]} ({block[2]}) and following it")
    if dry:
        return
    cit.home_block_id = __import__("uuid").UUID(block[0])
    await db.execute(text("""
        INSERT INTO block_subscriptions (user_id, block_id)
        VALUES (:u, :b) ON CONFLICT (user_id, block_id) DO NOTHING
    """), {"u": str(cit.id), "b": block[0]})
    await db.commit()
    await set_rls_context(db, bypass=True)


async def report(db) -> None:
    def show(label, rows):
        print(f"  {label:<28} {rows}")
    print("\nDatabase now holds:")
    show("sites", [r[0] for r in (await db.execute(
        text("SELECT name FROM isr_points ORDER BY name"))).all()])
    show("advisories by status", dict((await db.execute(
        text("SELECT status, count(*) FROM advisories GROUP BY 1"))).all()))
    show("alerts by kind", dict((await db.execute(
        text("SELECT kind, count(*) FROM alerts GROUP BY 1"))).all()))
    show("deliveries by status", dict((await db.execute(
        text("SELECT status, count(*) FROM alert_deliveries GROUP BY 1"))).all()))
    show("citizens with a home block", (await db.execute(text(
        "SELECT count(*) FROM users WHERE home_block_id IS NOT NULL"))).scalar())
    inbox = (await db.execute(text("""
        SELECT u.email, count(a.id)
        FROM users u
        JOIN block_subscriptions bs ON bs.user_id = u.id
        JOIN alerts a ON a.block_id = bs.block_id
        WHERE u.role = 'citizen'
        GROUP BY u.email ORDER BY 2 DESC
    """))).all()
    show("alerts per citizen inbox", dict(inbox))


async def run(args) -> int:
    _quiet_sql()
    async with AsyncSessionLocal() as db:
        await set_rls_context(db, bypass=True)
        admin = await _admin(db)
        logger.info(f"acting as the admin account {admin.email} (loaded by role, no password used)")
        await step_remove(db, args.remove, args.dry_run)
        site = await _site(db, args.site)
        await step_start_date(db, site, args.start, args.dry_run)
        await step_publish(db, site, admin, args.dry_run)
    await step_scan(args.dry_run)
    async with AsyncSessionLocal() as db:
        await set_rls_context(db, bypass=True)
        site = await _site(db, args.site)
        await step_citizen(db, site, args.citizen, args.dry_run)
        await report(db)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--site", default=DEFAULT_SITE)
    ap.add_argument("--remove", nargs="*", default=DEFAULT_REMOVE)
    ap.add_argument("--start", default="2010-01-01")
    ap.add_argument("--citizen", default=DEFAULT_CITIZEN)
    ap.add_argument("--dry-run", action="store_true")
    return asyncio.run(run(ap.parse_args()))


if __name__ == "__main__":
    sys.exit(main())
