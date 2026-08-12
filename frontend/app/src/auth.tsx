/** Session state, and the role predicates the UI branches on. */
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

/**
 * The four working roles. Mirrors `STAFF_ROLES` in `app/dependencies.py`, and
 * `citizen`/`viewer` are excluded for the same reason: design §2 forbids
 * non-staff a precise ISR coordinate. This is a rendering convenience only —
 * the guard that matters is the API's, and the RLS policy behind it.
 */
export const STAFF_ROLES: Role[] = ["admin", "regulator", "analyst", "field_officer"];
export const isStaff = (r?: Role) => !!r && STAFF_ROLES.includes(r);
export const canReview = (r?: Role) => r === "admin" || r === "regulator";
export const canRunSims = (r?: Role) => r === "admin" || r === "analyst";
export const canSync = (r?: Role) => r === "admin";

export function AuthProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // Resume a session from a stored token. The role is re-read from the
    // server rather than trusted from anything local, matching the backend,
    // which re-reads it from the database on every request.
    if (!getToken()) {
      setLoading(false);
      return;
    }
    auth
      .me()
      .then(setMe)
      .catch(() => clearToken())
      .finally(() => setLoading(false));
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

  function signOut() {
    clearToken();
    setMe(null);
  }

  return (
    <Ctx.Provider value={{ me, loading, error, signIn, signOut }}>{children}</Ctx.Provider>
  );
}

export function useAuth() {
  const v = useContext(Ctx);
  if (!v) throw new Error("useAuth outside AuthProvider");
  return v;
}
