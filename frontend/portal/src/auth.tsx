/**
 * Session and the role model the UI branches on.
 *
 * These predicates MIRROR the backend guards in `app/dependencies.py`; they do
 * not replace them. Hiding a control the API would refuse is a courtesy, not a
 * security boundary — every one of these is enforced again server-side and, for
 * site data, a third time by a Postgres row-level-security policy.
 */
import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { auth, clearToken, getToken, setToken, type Me, type Role } from "./api/client";

interface AuthState {
  me: Me | null;
  loading: boolean;
  error: string | null;
  signIn: (email: string, password: string) => Promise<void>;
  signOut: () => void;
}
const Ctx = createContext<AuthState | null>(null);

/** The four working roles. Excludes `citizen`, which design §2 forbids precise
 *  ISR coordinates — every site here is hypothetical, and publishing a point for
 *  a speculative mine beside a named village invites it being read as a plan. */
export const STAFF: Role[] = ["admin", "regulator", "analyst", "field_officer"];

export const isStaff    = (r?: Role) => !!r && STAFF.includes(r);
export const canReview  = (r?: Role) => r === "admin" || r === "regulator";
export const canRunSim  = (r?: Role) => r === "admin" || r === "analyst";
export const canSubmit  = (r?: Role) => r === "admin" || r === "field_officer";
export const canSync    = (r?: Role) => r === "admin";
export const canIngest  = (r?: Role) => r === "admin";
export const canAdmin   = (r?: Role) => r === "admin";
export const canAudit   = (r?: Role) => r === "admin" || r === "regulator";

export const ROLE_LABEL: Record<Role, string> = {
  admin: "Administrator",
  regulator: "Regulator",
  analyst: "Analyst",
  field_officer: "Field Officer",
  citizen: "Citizen",
  viewer: "Citizen (legacy)",
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
  admin: "Operate the platform: accounts, ingestion, dataset syncs and the audit trail.",
  regulator: "Decide: review field evidence, act on excursions, and sign off on findings.",
  analyst: "Investigate: build scenarios, run the plume engine, and compare outcomes.",
  field_officer: "Validate on the ground: submit observations for review.",
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

  const signOut = () => { clearToken(); setMe(null); };

  return <Ctx.Provider value={{ me, loading, error, signIn, signOut }}>{children}</Ctx.Provider>;
}

export function useAuth() {
  const v = useContext(Ctx);
  if (!v) throw new Error("useAuth outside AuthProvider");
  return v;
}
