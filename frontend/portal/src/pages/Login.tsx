/**
 * Sign in, and — new in P5 — citizen self-registration.
 *
 * WHY THERE IS A REGISTER FORM HERE AT ALL. The product requires citizens to
 * sign in, and account creation is otherwise admin-only (`POST /auth/signup`
 * was deleted in P2 as a verified privilege-escalation hole). Requiring a
 * resident to email an administrator for an account is not a citizen product,
 * so `POST /citizen/register` exists — with the role hard-pinned server-side
 * and no `role` field in its schema at all.
 */
import { useState, type FormEvent } from "react";
import { citizen, setToken, type Role } from "../api/client";
import { ROLE_COLOUR, ROLE_LABEL, useAuth } from "../auth";

/**
 * Demonstration accounts, one per role, for local development ONLY.
 *
 * DEPLOYMENT AUDIT F-1 (P0). These used to be a plain module-level constant, so
 * they were compiled into the production bundle: `grep admin123 dist/assets/*.js`
 * returned a hit, and with it a working **admin** password for anyone who
 * viewed source. Admin can publish advisories to residents, run the factory
 * reset, rewrite datasets and read the audit log. That is total compromise, and
 * it shipped as a convenience for reviewers.
 *
 * `import.meta.env.DEV` is a compile-time constant in Vite, not a runtime flag.
 * A production build substitutes `false`, so the whole branch — the strings
 * included — is removed by dead-code elimination rather than merely hidden. A
 * runtime check would have kept the passwords in the bundle, which is the bug.
 *
 * Guarded by `tests/no-credentials-in-bundle.mjs`, which greps the built
 * artifact and fails the build if any of them survives.
 */
const DEMO: Array<{ email: string; password: string; role: Role }> =
  import.meta.env.DEV
    ? [
        { email: "admin@jaldrishti.local", password: "admin123", role: "admin" },
        { email: "analyst@jaldrishti.local", password: "analyst123", role: "analyst" },
        { email: "field@jaldrishti.local", password: "field123", role: "field_officer" },
        { email: "citizen@jaldrishti.local", password: "citizen123", role: "citizen" },
      ]
    : [];

export default function Login() {
  const { signIn, error } = useAuth();
  const [mode, setMode] = useState<"in" | "up">("in");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [username, setUsername] = useState("");
  const [busy, setBusy] = useState(false);
  const [regError, setRegError] = useState<string | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setRegError(null);
    try {
      if (mode === "in") {
        await signIn(email, password);
      } else {
        const r = await citizen.register(username, email, password);
        // Registering signs you in. A second sign-in step after creating an
        // account is a drop-off point that buys nothing.
        setToken(r.access_token);
        window.location.reload();
      }
    } catch (err) {
      if (mode === "up") {
        setRegError(err instanceof Error ? err.message : "Could not create the account.");
      }
      /* sign-in errors are surfaced by the auth context */
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login">
      <form className="login-card" onSubmit={submit}>
        <div className="row" style={{ marginBottom: 14 }}>
          <div className="hdr-mark" style={{ width: 36, height: 36 }} aria-hidden>💧</div>
          <div>
            <h1 className="hdr-name" style={{ fontSize: "var(--fs-xl)" }}>JalDrishti</h1>
            <div className="hdr-sub">ISR Groundwater Monitoring Portal</div>
          </div>
        </div>

        <div className="seg" style={{ marginBottom: 16 }}>
          <button type="button" className={mode === "in" ? "active" : ""}
                  onClick={() => setMode("in")}>Sign in</button>
          <button type="button" className={mode === "up" ? "active" : ""}
                  onClick={() => setMode("up")}>Create an account</button>
        </div>

        {mode === "in" && error && (
          <div className="banner danger" style={{ marginBottom: 13 }}>{error}</div>
        )}
        {mode === "up" && regError && (
          <div className="banner danger" style={{ marginBottom: 13 }}>{regError}</div>
        )}

        {mode === "up" && (
          <>
            <div className="banner" style={{ marginBottom: 13 }}>
              Creating an account here gives you the <strong>resident</strong> view:
              groundwater test results for the areas you follow, and alerts when they
              change. Government and technical accounts are issued by an administrator.
            </div>
            <div className="field">
              <label htmlFor="u">Your name</label>
              <input id="u" value={username} autoComplete="name" required
                     minLength={3} onChange={(ev) => setUsername(ev.target.value)} />
            </div>
          </>
        )}

        <div className="field">
          <label htmlFor="e">Email</label>
          <input id="e" type="email" value={email} autoComplete="username" required
                 onChange={(ev) => setEmail(ev.target.value)} />
        </div>
        <div className="field">
          <label htmlFor="p">Password</label>
          <input id="p" type="password" value={password} required
                 minLength={mode === "up" ? 8 : undefined}
                 autoComplete={mode === "up" ? "new-password" : "current-password"}
                 onChange={(ev) => setPassword(ev.target.value)} />
          {mode === "up" && (
            <div className="hint">At least 8 characters.</div>
          )}
        </div>

        <button className="btn primary lg" style={{ width: "100%" }} disabled={busy}>
          {busy
            ? (mode === "in" ? "Signing in…" : "Creating your account…")
            : (mode === "in" ? "Sign in" : "Create account")}
        </button>

        {mode === "in" && DEMO.length > 0 && (
          <div className="demo-users">
            <div className="muted small" style={{ marginBottom: 7 }}>
              Demonstration accounts — one per role. Click to fill.
            </div>
            {DEMO.map((d) => (
              <button key={d.email} type="button" className="demo-user"
                      onClick={() => { setEmail(d.email); setPassword(d.password); }}>
                <span className="role-pill" style={{ color: ROLE_COLOUR[d.role] }}>
                  {ROLE_LABEL[d.role]}
                </span>
                <span className="mono muted">{d.email}</span>
              </button>
            ))}
          </div>
        )}

        {/* Design §4.5 rule 6 — the premise is never more than one glance away. */}
        <div className="banner warn" style={{ marginTop: 15 }}>
          <strong>No ISR uranium mine operates in Jharkhand.</strong> Every site in this
          system is hypothetical. The portal is for screening, preparedness and
          research — never permitting.
        </div>
      </form>
    </div>
  );
}
