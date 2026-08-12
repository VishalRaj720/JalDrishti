import { useState, type FormEvent } from "react";
import { ROLE_COLOUR, ROLE_LABEL, useAuth } from "../auth";
import type { Role } from "../api/client";

/** Demonstration accounts, one per role. Listed so a reviewer can walk every
 *  role's portal without hunting for credentials. Weak on purpose, and the
 *  caption says so rather than implying these belong in a deployment. */
const DEMO: Array<{ email: string; password: string; role: Role }> = [
  { email: "admin@jaldrishti.local", password: "admin123", role: "admin" },
  { email: "regulator@jaldrishti.local", password: "regulator123", role: "regulator" },
  { email: "analyst@jaldrishti.local", password: "analyst123", role: "analyst" },
  { email: "field@jaldrishti.local", password: "field123", role: "field_officer" },
  { email: "citizen@jaldrishti.local", password: "citizen123", role: "citizen" },
];

export default function Login() {
  const { signIn, error } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    try { await signIn(email, password); } catch { /* shown below */ }
    finally { setBusy(false); }
  }

  return (
    <div className="login">
      <form className="login-card" onSubmit={submit}>
        <div className="row" style={{ marginBottom: 14 }}>
          <div className="hdr-mark" style={{ width: 36, height: 36 }}>💧</div>
          <div>
            <h1 className="hdr-name" style={{ fontSize: 21 }}>JalDrishti</h1>
            <div className="hdr-sub">ISR Groundwater Monitoring Portal</div>
          </div>
        </div>

        {error && <div className="banner danger" style={{ marginBottom: 13 }}>{error}</div>}

        <div className="field">
          <label htmlFor="e">Email</label>
          <input id="e" type="email" value={email} autoComplete="username"
                 onChange={(ev) => setEmail(ev.target.value)} required />
        </div>
        <div className="field">
          <label htmlFor="p">Password</label>
          <input id="p" type="password" value={password} autoComplete="current-password"
                 onChange={(ev) => setPassword(ev.target.value)} required />
        </div>
        <button className="btn primary" style={{ width: "100%" }} disabled={busy}>
          {busy ? "Signing in…" : "Sign in"}
        </button>

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
