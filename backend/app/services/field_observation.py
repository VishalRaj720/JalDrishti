"""Submit / review workflow for field observations.

THE GUARANTEE THIS MODULE EXISTS TO KEEP: nothing a field officer submits
reaches the authoritative dataset — or therefore any calculation reading it —
until a reviewer who is not the submitter approves it.

Five things enforce that, deliberately layered so no single mistake defeats it:

1. **Pending proposals are not in the authoritative tables at all.** They sit in
   `field_observations`. A query against `water_samples` cannot see unreviewed
   data even if it forgets to filter, because there is nothing to filter.
2. **`ck_field_obs_no_self_review`** makes `reviewed_by = submitted_by`
   unrepresentable in the schema. The check below is the friendly error; the
   constraint is the guarantee.
3. **The API guard** restricts approve/reject to admin and regulator.
4. **An allowlist per observation type** bounds what a payload may set, so the
   approval path cannot write to a column nobody reviewed (`synthetic`, ids).
5. **A fingerprint of the target row** is taken at submit time and rechecked at
   approval, so approving a stale proposal cannot silently clobber a newer edit.

Every transition writes an audit record carrying the old and new values.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import (AppException, AuthorizationError,
                            ResourceNotFoundError)
from app.models.field_observation import (
    ALLOWED_FIELDS, DATETIME_FIELDS, REQUIRED_FIELDS, TARGET_TABLES,
    UUID_FIELDS, FieldObservation, ObservationOperation, ObservationStatus,
    ObservationType,
)
from app.models.user import User, UserRole
from app.services import audit

REVIEWER_ROLES = (UserRole.admin, UserRole.regulator)


class AppValidationError(AppException):
    def __init__(self, message: str):
        super().__init__(message, status_code=422)


class ConflictError(AppException):
    def __init__(self, message: str):
        super().__init__(message, status_code=409)


def _fingerprint(payload: Optional[dict[str, Any]]) -> Optional[str]:
    """Stable digest of a row snapshot, for staleness detection."""
    if payload is None:
        return None
    canonical = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


def _coerce_binds(obs_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Turn JSON scalars into the Python types asyncpg binds by.

    asyncpg dispatches on the Python type, not on the column, so an ISO string
    bound to a `timestamptz` raises DataError rather than being parsed. JSONB
    round-trips these as strings, so the conversion has to happen every time the
    payload is used, not once at submit.
    """
    out = dict(payload)
    for key in DATETIME_FIELDS.get(obs_type, ()):
        v = out.get(key)
        if isinstance(v, str):
            # fromisoformat handles '+00:00' but not the 'Z' suffix before 3.11
            out[key] = datetime.fromisoformat(v.replace("Z", "+00:00"))
    for key in UUID_FIELDS.get(obs_type, ()):
        v = out.get(key)
        if isinstance(v, str):
            out[key] = uuid.UUID(v)
    return out


def _jsonable(row: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in row.items():
        if isinstance(v, (datetime,)):
            out[k] = v.isoformat()
        elif isinstance(v, uuid.UUID):
            out[k] = str(v)
        else:
            out[k] = v
    return out


class FieldObservationService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ── validation ───────────────────────────────────────────────────

    def _validate(self, obs_type: str, operation: str,
                  payload: Optional[dict[str, Any]]) -> dict[str, Any]:
        if obs_type not in TARGET_TABLES:
            raise AppValidationError(f"Unknown observation_type '{obs_type}'.")
        if operation not in {o.value for o in ObservationOperation}:
            raise AppValidationError(f"Unknown operation '{operation}'.")

        if operation == ObservationOperation.delete.value:
            return {}
        if not payload:
            raise AppValidationError("A create or update needs a payload.")

        allowed = ALLOWED_FIELDS[obs_type]
        unknown = set(payload) - allowed
        if unknown:
            # Rejected, not dropped: silently ignoring a field would let a
            # submitter believe they had recorded something they had not.
            raise AppValidationError(
                f"Fields not permitted for {obs_type}: {sorted(unknown)}. "
                f"Allowed: {sorted(allowed)}")
        if operation == ObservationOperation.create.value:
            missing = REQUIRED_FIELDS[obs_type] - set(payload)
            if missing:
                raise AppValidationError(
                    f"Missing required fields for {obs_type}: {sorted(missing)}")
        if obs_type == ObservationType.ore_presence.value:
            zone = payload.get("ore_zone")
            if zone is not None and zone not in ("deposit", "belt", "none"):
                raise AppValidationError(
                    "ore_zone must be one of: deposit, belt, none")
            grade = payload.get("uranium_grade_pct")
            if grade is not None and not (0 <= float(grade) <= 100):
                raise AppValidationError(
                    "uranium_grade_pct must be between 0 and 100")

        # Parse timestamps and ids now so a malformed value is the submitter's
        # error, not something the reviewer discovers at approval time.
        try:
            _coerce_binds(obs_type, payload)
        except (ValueError, TypeError) as exc:
            raise AppValidationError(f"Invalid field value: {exc}")
        return payload

    async def _snapshot(self, table: str, target_id: uuid.UUID
                        ) -> Optional[dict[str, Any]]:
        """Read the authoritative row so old/new can be recorded."""
        # `table` is never user input: it comes from TARGET_TABLES.
        res = await self.db.execute(
            text(f"SELECT * FROM {table} WHERE id = :i"), {"i": str(target_id)})
        row = res.mappings().first()
        if row is None:
            return None
        d = dict(row)
        d.pop("location", None)     # geography objects are not JSON-serialisable
        return _jsonable(d)

    # ── submit ───────────────────────────────────────────────────────

    async def submit(
        self, *, actor: User, observation_type: str, operation: str,
        payload: Optional[dict[str, Any]] = None,
        target_id: Optional[uuid.UUID] = None,
        note: Optional[str] = None, ip: Optional[str] = None,
    ) -> FieldObservation:
        payload = self._validate(observation_type, operation, payload)
        table = TARGET_TABLES[observation_type]

        previous = None
        if operation in (ObservationOperation.update.value,
                         ObservationOperation.delete.value):
            if target_id is None:
                raise AppValidationError(
                    f"operation '{operation}' requires target_id.")
            previous = await self._snapshot(table, target_id)
            if previous is None:
                raise ResourceNotFoundError(table, str(target_id))
        elif target_id is not None:
            raise AppValidationError("operation 'create' must not set target_id.")

        obs = FieldObservation(
            observation_type=observation_type,
            operation=operation,
            target_table=table,
            target_id=target_id,
            proposed=(payload or None),
            previous=previous,
            target_fingerprint=_fingerprint(previous),
            note=note,
            status=ObservationStatus.pending.value,
            submitted_by=actor.id,
            org_id=actor.org_id,
        )
        if observation_type == ObservationType.ore_presence.value and payload:
            lon, lat = payload.get("longitude"), payload.get("latitude")
            if lon is not None and lat is not None:
                obs.location = f"SRID=4326;POINT({float(lon)} {float(lat)})"

        self.db.add(obs)
        await self.db.flush()
        await self.db.commit()

        await audit.record(
            action="field_observation.submit", entity_type="field_observations",
            entity_id=str(obs.id), actor_id=actor.id, actor_label=actor.email,
            ip_address=ip,
            detail={"observation_type": observation_type, "operation": operation,
                    "target_table": table,
                    "target_id": str(target_id) if target_id else None,
                    "old": previous, "new": payload or None,
                    "status": ObservationStatus.pending.value},
        )
        return obs

    # ── queries ──────────────────────────────────────────────────────

    async def get(self, obs_id: uuid.UUID) -> FieldObservation:
        obs = (await self.db.execute(
            select(FieldObservation).where(FieldObservation.id == obs_id)
        )).scalar_one_or_none()
        if obs is None:
            # RLS may also be hiding another officer's row; 404 either way, so
            # the response does not confirm that an id exists.
            raise ResourceNotFoundError("FieldObservation", str(obs_id))
        return obs

    async def list(self, *, status: Optional[str] = None,
                   observation_type: Optional[str] = None,
                   limit: int = 100, offset: int = 0) -> list[FieldObservation]:
        stmt = select(FieldObservation).order_by(
            FieldObservation.submitted_at.desc())
        if status:
            stmt = stmt.where(FieldObservation.status == status)
        if observation_type:
            stmt = stmt.where(
                FieldObservation.observation_type == observation_type)
        res = await self.db.execute(stmt.offset(offset).limit(limit))
        return list(res.scalars().all())

    # ── submitter-side edits ─────────────────────────────────────────

    async def withdraw(self, *, actor: User, obs_id: uuid.UUID,
                       ip: Optional[str] = None) -> FieldObservation:
        obs = await self.get(obs_id)
        if obs.submitted_by != actor.id:
            raise AuthorizationError("Only the submitter may withdraw a proposal.")
        if obs.status != ObservationStatus.pending.value:
            raise ConflictError(
                f"Cannot withdraw a proposal in status '{obs.status}'.")
        obs.status = ObservationStatus.withdrawn.value
        await self.db.commit()
        await audit.record(
            action="field_observation.withdraw",
            entity_type="field_observations", entity_id=str(obs.id),
            actor_id=actor.id, actor_label=actor.email, ip_address=ip,
            detail={"status": obs.status},
        )
        return obs

    # ── review ───────────────────────────────────────────────────────

    async def _assert_reviewable(self, obs: FieldObservation, actor: User) -> None:
        if actor.role not in REVIEWER_ROLES:
            raise AuthorizationError(
                f"Role '{actor.role.value}' may not review field observations.")
        if obs.submitted_by == actor.id:
            # Also guaranteed by ck_field_obs_no_self_review; this is the
            # readable 403 rather than an IntegrityError.
            raise AuthorizationError(
                "A submitter may not review their own field observation.")
        if obs.status != ObservationStatus.pending.value:
            raise ConflictError(
                f"Proposal is already '{obs.status}'; only pending proposals "
                f"can be reviewed.")

    async def reject(self, *, actor: User, obs_id: uuid.UUID,
                     review_note: Optional[str] = None,
                     ip: Optional[str] = None) -> FieldObservation:
        obs = await self.get(obs_id)
        await self._assert_reviewable(obs, actor)

        obs.status = ObservationStatus.rejected.value
        obs.reviewed_by = actor.id
        obs.reviewed_at = datetime.now(timezone.utc)
        obs.review_note = review_note
        await self.db.commit()

        await audit.record(
            action="field_observation.reject",
            entity_type="field_observations", entity_id=str(obs.id),
            actor_id=actor.id, actor_label=actor.email, ip_address=ip,
            detail={"status": "rejected", "review_note": review_note,
                    "submitted_by": str(obs.submitted_by),
                    "old": obs.previous, "new": obs.proposed,
                    "applied": False},
        )
        return obs

    async def approve(self, *, actor: User, obs_id: uuid.UUID,
                      review_note: Optional[str] = None,
                      ip: Optional[str] = None) -> FieldObservation:
        obs = await self.get(obs_id)
        await self._assert_reviewable(obs, actor)

        # Staleness: if the authoritative row moved since the proposal was
        # written, applying it would silently overwrite the newer edit.
        if obs.operation in (ObservationOperation.update.value,
                             ObservationOperation.delete.value):
            current = await self._snapshot(obs.target_table, obs.target_id)
            if current is None:
                raise ConflictError(
                    f"Target {obs.target_table}/{obs.target_id} no longer "
                    f"exists; the proposal cannot be applied.")
            if _fingerprint(current) != obs.target_fingerprint:
                raise ConflictError(
                    "The target row changed after this proposal was submitted. "
                    "Approving would overwrite the newer value. Ask the "
                    "submitter to resubmit against the current record.")

        applied_id = await self._apply(obs, actor)

        obs.status = ObservationStatus.approved.value
        obs.reviewed_by = actor.id
        obs.reviewed_at = datetime.now(timezone.utc)
        obs.review_note = review_note
        obs.applied_id = applied_id
        await self.db.commit()

        await audit.record(
            action="field_observation.approve",
            entity_type="field_observations", entity_id=str(obs.id),
            actor_id=actor.id, actor_label=actor.email, ip_address=ip,
            detail={"status": "approved", "review_note": review_note,
                    "submitted_by": str(obs.submitted_by),
                    "target_table": obs.target_table,
                    "applied_id": str(applied_id) if applied_id else None,
                    "old": obs.previous, "new": obs.proposed,
                    "applied": True},
        )
        return obs

    # ── applying an approved proposal ────────────────────────────────

    async def _apply(self, obs: FieldObservation, actor: User
                     ) -> Optional[uuid.UUID]:
        """Write the authoritative row. Runs inside the approval transaction, so
        a failure here leaves the proposal pending rather than half-applied."""
        table = obs.target_table
        if table not in TARGET_TABLES.values():
            raise AppValidationError(f"Refusing to write unknown table '{table}'.")

        # `ore_observations` is writable only under the system bypass (see the
        # ore_obs_write policy), which is exactly this path: the approval, not
        # the submitter, is what authorises the write.
        from app.database import set_rls_context
        await set_rls_context(self.db, bypass=True)

        try:
            if obs.operation == ObservationOperation.delete.value:
                await self.db.execute(
                    text(f"DELETE FROM {table} WHERE id = :i"),
                    {"i": str(obs.target_id)})
                return obs.target_id

            payload = dict(obs.proposed or {})

            if obs.observation_type == ObservationType.ore_presence.value:
                return await self._apply_ore(obs, payload, actor)

            binds = _coerce_binds(obs.observation_type, payload)

            if obs.operation == ObservationOperation.create.value:
                # `id` is not in ALLOWED_FIELDS on purpose — a submitter must
                # not choose a primary key, or they could target an existing
                # row. These tables set it from the ORM rather than a database
                # default, so this raw INSERT has to supply it.
                binds = {"id": uuid.uuid4(), **binds}
                cols = list(binds)
                collist = ", ".join(cols)
                vals = ", ".join(f":{c}" for c in cols)
                res = await self.db.execute(
                    text(f"INSERT INTO {table} ({collist}) VALUES ({vals}) "
                         f"RETURNING id"), binds)
                return res.scalar_one()

            sets = ", ".join(f"{c} = :{c}" for c in binds)
            params = {**binds, "i": str(obs.target_id)}
            await self.db.execute(
                text(f"UPDATE {table} SET {sets} WHERE id = :i"), params)
            return obs.target_id
        finally:
            # Restore the reviewer's own context for the rest of the
            # transaction. If the apply above failed, the transaction is already
            # aborted and this would raise InFailedSQLTransactionError — which
            # would REPLACE the real error and leave the reviewer with a
            # meaningless message. The original exception must win.
            try:
                await set_rls_context(
                    self.db, role=actor.role.value,
                    org_id=(str(actor.org_id) if actor.org_id else None),
                    user_id=str(actor.id))
            except Exception:  # noqa: BLE001
                pass

    async def _apply_ore(self, obs: FieldObservation, payload: dict[str, Any],
                         actor: User) -> uuid.UUID:
        payload = _coerce_binds(obs.observation_type, payload)
        lon = payload.pop("longitude", None)
        lat = payload.pop("latitude", None)
        if obs.operation == ObservationOperation.create.value:
            new_id = uuid.uuid4()
            await self.db.execute(text("""
                INSERT INTO ore_observations
                    (id, name, location, ore_zone, uranium_grade_pct, depth_m,
                     observed_at, notes, origin_observation_id, created_by)
                VALUES
                    (:id, :name,
                     ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography,
                     :ore_zone, :grade, :depth, :observed_at, :notes, :origin, :by)
            """), {
                "id": str(new_id), "name": payload.get("name"),
                "lon": float(lon), "lat": float(lat),
                "ore_zone": payload.get("ore_zone"),
                "grade": payload.get("uranium_grade_pct"),
                "depth": payload.get("depth_m"),
                "observed_at": payload.get("observed_at"),
                "notes": payload.get("notes"),
                "origin": str(obs.id), "by": str(obs.submitted_by),
            })
            return new_id

        sets, params = [], {"i": str(obs.target_id)}
        for col, key in (("name", "name"), ("ore_zone", "ore_zone"),
                         ("uranium_grade_pct", "uranium_grade_pct"),
                         ("depth_m", "depth_m"), ("observed_at", "observed_at"),
                         ("notes", "notes")):
            if key in payload:
                sets.append(f"{col} = :{key}")
                params[key] = payload[key]
        if lon is not None and lat is not None:
            sets.append("location = ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography")
            params["lon"], params["lat"] = float(lon), float(lat)
        if sets:
            await self.db.execute(
                text(f"UPDATE ore_observations SET {', '.join(sets)} WHERE id = :i"),
                params)
        return obs.target_id
