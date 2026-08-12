import { useState, type FormEvent } from "react";
import { useAuth } from "../auth";

export default function Login() {
  const { signIn, error } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      await signIn(email, password);
    } catch {
      /* `error` from the context is already rendered below */
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login-wrap">
      <form className="login-card" onSubmit={onSubmit}>
        <h1>JalDrishti</h1>
        <p className="sub">
          Groundwater contamination assessment for Jharkhand. Sign in to continue.
        </p>

        {error && (
          <div className="error" style={{ marginBottom: "var(--sp-4)" }}>
            {error}
          </div>
        )}

        <div className="field">
          <label htmlFor="email">Email</label>
          <input
            id="email"
            type="email"
            value={email}
            autoComplete="username"
            onChange={(e) => setEmail(e.target.value)}
            required
          />
        </div>
        <div className="field">
          <label htmlFor="password">Password</label>
          <input
            id="password"
            type="password"
            value={password}
            autoComplete="current-password"
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </div>

        <button className="primary" style={{ width: "100%" }} disabled={busy}>
          {busy ? "Signing in…" : "Sign in"}
        </button>

        {/* The premise is never more than one glance away (design §4.5 rule 6). */}
        <p className="muted" style={{ marginTop: "var(--sp-5)", lineHeight: 1.5 }}>
          No ISR uranium mine operates in Jharkhand. Every site in this system is{" "}
          <strong>hypothetical</strong>; simulations are for screening and
          preparedness, not permitting.
        </p>
      </form>
    </div>
  );
}
