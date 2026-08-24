/**
 * Session and the role model the UI branches on.
 *
 * These predicates MIRROR the backend guards in `app/dependencies.py`; they do
 * not replace them. Hiding a control the API would refuse is a courtesy, not a
 * security boundary — every one of these is enforced again server-side and, for
 * site data, a third time by a Postgres row-level-security policy.
 */
import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import {
  auth, clearToken, getToken, setToken, tokenSecondsLeft, type Me, type Role,
} from "./api/client";

interface AuthState {
  me: Me | null;
  loading: boolean;
  error: string | null;
  signIn: (email: string, password: string) => Promise<void>;
  signOut: () => void;
}
const Ctx = createContext<AuthState | null>(null);

/** The three working roles. Excludes `citizen`, which design §2 forbids precise
 *  ISR coordinates — every site here is hypothetical, and publishing a point for
 *  a speculative mine beside a named village invites it being read as a plan.
 *
 *  R12 restored `regulator` with a narrower job than it had before R7:
 *  reviewing what a field officer submits, and nothing else. It is staff
 *  because the review queue is staff-only, and it is deliberately excluded from
 *  every dataset, model and account capability below — a regulator accepts
 *  evidence into the record, an admin operates the pipeline that consumes it.
 *
 *  There is exactly ONE admin and there may be MANY regulators. */
export const STAFF: Role[] = ["admin", "analyst", "field_officer", "regulator"];

export const isStaff    = (r?: Role) => !!r && STAFF.includes(r);
/** Deciding on a FIELD OFFICER'S SUBMISSION — approve or reject. */
export const canReview  = (r?: Role) => r === "admin" || r === "regulator";
/** Deciding whether a screening reaches residents. Admin only, deliberately:
 *  accepting evidence and announcing a modelled result to a village are
 *  different decisions, and R12 restored only the first to the regulator. */
export const canPublish = (r?: Role) => r === "admin";
//: Regulator added 2026-08-25: a CGWB/SPCB officer asking "what would happen
//: if" is the primary real-world user of a screening tool. Publication stays
//: `canPublish` (admin only) — running a model and announcing its result to
//: a village are different authorities.
export const canRunSim  = (r?: Role) =>
  r === "admin" || r === "regulator" || r === "analyst";
export const canSubmit  = (r?: Role) => r === "admin" || r === "field_officer";
export const canSync    = (r?: Role) => r === "admin";
export const canIngest  = (r?: Role) => r === "admin";
export const canAdmin   = (r?: Role) => r === "admin";
/** Reading everyone's history is an operator power. A regulator's own
 *  decisions are written to the trail, but they do not read it. */
export const canAudit   = (r?: Role) => r === "admin";

export const ROLE_LABEL: Record<Role, string> = {
  admin: "Administrator",
  analyst: "Analyst",
  // Renamed from "Field Officer": this project does no fieldwork. They submit
  // uranium-ore occurrences from published geology, which is a different job
  // and deserves a title that does not overstate it.
  field_officer: "Data Submitter",
  citizen: "Resident",
  regulator: "Regulator",
  viewer: "Resident (legacy)",
};

export const ROLE_COLOUR: Record<Role, string> = {
  admin: "var(--role-admin)",
  regulator: "var(--role-regulator)",
  analyst: "var(--role-analyst)",
  field_officer: "var(--role-field)",
  citizen: "var(--role-citizen)",
  viewer: "var(--role-citizen)",
};

/** One line per role explaining what this portal is *for them*. */
export const ROLE_PURPOSE: Record<Role, string> = {
  admin: "Operate and decide: accounts, ingestion, syncs, the audit trail, and what gets published to residents.",
  regulator: "Review: decide whether a data submitter's finding is accepted into the record.",

  analyst: "Investigate: build scenarios, run the plume engine, and compare outcomes.",
  field_officer: "Contribute evidence: submit uranium-ore occurrences for review.",
  citizen: "Understand: what the groundwater near you actually measures.",
  viewer: "Understand: what the groundwater near you actually measures.",
};

export function AuthProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!getToken()) { setLoading(false); return; }
    // The role is re-read from the server, never trusted from anything local —
    // matching the backend, which re-reads it from the database per request so
    // a demotion takes effect immediately rather than at token expiry.
    auth.me().then(setMe).catch(() => clearToken()).finally(() => setLoading(false));
  }, []);

  async function signIn(email: string, password: string) {
    setError(null);
    try {
      const { access_token } = await auth.login(email, password);
      setToken(access_token);
      setMe(await auth.me());
    } catch (e) {
      clearToken();
      setError(e instanceof Error ? e.message : "Sign-in failed.");
      throw e;
    }
  }

  const signOut = () => {
    // Fire-and-forget: the local session ends immediately either way. Awaiting
    // it would make a slow network look like a broken Sign out button.
    void auth.logout();
    clearToken();
    setMe(null);
  };

  /**
   * Keep an active session alive (R11, finding O-9).
   *
   * `.env` sets a 15-minute token while `config.py` defaults to 480, and there
   * was no refresh path at all: a 401 clears the token, so anyone reading a long
   * report or filling in a submission form was signed out mid-task and lost what
   * they had typed. I hit this myself while verifying a page.
   *
   * The timer is derived from the token's own `exp` rather than a constant,
   * because the lifetime is server configuration and a hard-coded client value
   * would be wrong in one deployment or the other. It fires at half of the
   * remaining life, floored at 30 s so a very short token cannot spin, and only
   * while a user is actually signed in — this extends an *active* session and
   * cannot resurrect an expired one.
   */
  useEffect(() => {
    if (!me) return;
    let timer: number | undefined;

    const schedule = () => {
      const left = tokenSecondsLeft();
      if (left === null) return;
      if (left <= 0) { clearToken(); setMe(null); return; }
      const delay = Math.max(30, Math.floor(left / 2));
      timer = window.setTimeout(async () => {
        try {
          const { access_token } = await auth.refresh();
          setToken(access_token);
          schedule();
        } catch {
          // Refusing to loop on a dead session: the next API call will 401 and
          // the user is sent to sign in with a message, which is honest.
        }
      }, delay * 1000);
    };

    schedule();
    return () => { if (timer) window.clearTimeout(timer); };
  }, [me]);

  return <Ctx.Provider value={{ me, loading, error, signIn, signOut }}>{children}</Ctx.Provider>;
}

export function useAuth() {
  const v = useContext(Ctx);
  if (!v) throw new Error("useAuth outside AuthProvider");
  return v;
}
