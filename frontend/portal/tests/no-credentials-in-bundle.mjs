/**
 * Fail the build if a credential survives into the production bundle.
 *
 * DEPLOYMENT AUDIT F-1 (P0). `Login.tsx` listed four demonstration accounts as a
 * module-level constant so reviewers could walk each role. Vite compiled them
 * into `dist/assets/index-*.js`, which meant every visitor to the deployed site
 * could read a working **admin** password. Admin publishes advisories to
 * residents, runs the factory reset, rewrites the datasets and reads the audit
 * log — so this was full compromise via view-source, shipped as a convenience.
 *
 * The fix puts the list behind `import.meta.env.DEV`, which Vite substitutes at
 * compile time so the strings are dead-code-eliminated. This checks that the
 * elimination actually happened, because the failure is invisible: the login
 * screen looks correct either way, and the passwords sit in a minified file
 * nobody opens.
 *
 * Run after `vite build`:  node tests/no-credentials-in-bundle.mjs
 */
import { readdirSync, readFileSync, existsSync } from "node:fs";
import { join } from "node:path";

const DIST = join(process.cwd(), "dist");

/** Literal secrets that must never reach a built artifact. */
const FORBIDDEN = [
  "admin123",
  "analyst123",
  "field123",
  "citizen123",
  "@jaldrishti.local",
];

if (!existsSync(DIST)) {
  console.error("no dist/ — run `npm run build` first");
  process.exit(2);
}

function walk(dir) {
  const out = [];
  for (const e of readdirSync(dir, { withFileTypes: true })) {
    const p = join(dir, e.name);
    if (e.isDirectory()) out.push(...walk(p));
    else out.push(p);
  }
  return out;
}

const files = walk(DIST).filter((f) => /\.(js|css|html|map)$/.test(f));
const hits = [];

for (const f of files) {
  const text = readFileSync(f, "utf8");
  for (const needle of FORBIDDEN) {
    if (text.includes(needle)) hits.push({ file: f.replace(DIST, "dist"), needle });
  }
}

if (hits.length) {
  console.error("\nCREDENTIALS FOUND IN THE PRODUCTION BUNDLE\n");
  for (const h of hits) console.error(`  ${h.file}  contains  ${h.needle}`);
  console.error(
    "\nThis is deployment audit finding F-1. The demo accounts must sit behind\n" +
    "`import.meta.env.DEV` so Vite eliminates them at build time. A runtime\n" +
    "check is NOT sufficient — it hides the buttons and keeps the passwords.\n");
  process.exit(1);
}

console.log(`no credentials in ${files.length} built files — F-1 guard passed`);
