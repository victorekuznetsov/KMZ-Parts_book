/* Shared auth crypto — runs on the Vercel Edge runtime AND on Node (build
   script), so it uses only Web Crypto (globalThis.crypto.subtle) and
   btoa/atob. No dependencies.

   - Passwords: PBKDF2-SHA256 (per-user salt) — hashes are safe to commit.
   - Session cookie: compact HMAC-SHA256 token  payload.signature  (base64url),
     signed with AUTH_SECRET. Carries { u, r, exp } and self-expires. */

const PBKDF2_ITERS = 120000;
const enc = new TextEncoder();
const dec = new TextDecoder();

// The HMAC signing secret. MUST be set on Vercel: Settings → Environment
// Variables → AUTH_SECRET (generate one with `node build/make_user.mjs secret`).
// There is deliberately no fallback value committed to the repo — if
// AUTH_SECRET is missing, every login/session check fails closed (nobody
// gets in) instead of falling back to a secret anyone reading this file
// could also read. Rotating AUTH_SECRET invalidates every existing session.
export function getSecret() {
  try {
    if (typeof process !== "undefined" && process.env && process.env.AUTH_SECRET)
      return process.env.AUTH_SECRET;
  } catch (e) {}
  throw new Error("AUTH_SECRET is not set (Vercel → Settings → Environment Variables)");
}

export function b64urlEncode(bytes) {
  const u8 = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes);
  let bin = "";
  for (let i = 0; i < u8.length; i++) bin += String.fromCharCode(u8[i]);
  return btoa(bin).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}
export function b64urlDecode(str) {
  let s = String(str || "").replace(/-/g, "+").replace(/_/g, "/");
  while (s.length % 4) s += "=";
  const bin = atob(s);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

export function randomBytes(n) {
  const b = new Uint8Array(n);
  crypto.getRandomValues(b);
  return b;
}

// ---- passwords (PBKDF2) ----------------------------------------------------
export async function pbkdf2(password, saltBytes, iters) {
  const keyMat = await crypto.subtle.importKey("raw", enc.encode(password), "PBKDF2", false, ["deriveBits"]);
  const bits = await crypto.subtle.deriveBits(
    { name: "PBKDF2", salt: saltBytes, iterations: iters || PBKDF2_ITERS, hash: "SHA-256" },
    keyMat, 256);
  return new Uint8Array(bits);
}
export async function hashPassword(password) {
  const salt = randomBytes(16);
  const h = await pbkdf2(password, salt, PBKDF2_ITERS);
  return { salt: b64urlEncode(salt), hash: b64urlEncode(h), iters: PBKDF2_ITERS };
}
export async function verifyPassword(password, rec) {
  if (!rec || !rec.salt || !rec.hash) return false;
  const h = await pbkdf2(password, b64urlDecode(rec.salt), rec.iters || PBKDF2_ITERS);
  const expected = b64urlDecode(rec.hash);
  if (h.length !== expected.length) return false;
  let diff = 0;
  for (let i = 0; i < h.length; i++) diff |= h[i] ^ expected[i];
  return diff === 0;
}

// ---- session token (HMAC) --------------------------------------------------
async function hmacKey(secret) {
  return crypto.subtle.importKey("raw", enc.encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign", "verify"]);
}
export async function signToken(payload, secret) {
  const body = b64urlEncode(enc.encode(JSON.stringify(payload)));
  const key = await hmacKey(secret);
  const sig = await crypto.subtle.sign("HMAC", key, enc.encode(body));
  return body + "." + b64urlEncode(sig);
}
export async function verifyToken(token, secret) {
  if (!token || typeof token !== "string" || token.indexOf(".") < 0) return null;
  const dot = token.indexOf(".");
  const body = token.slice(0, dot), sig = token.slice(dot + 1);
  const key = await hmacKey(secret);
  let ok = false;
  try { ok = await crypto.subtle.verify("HMAC", key, b64urlDecode(sig), enc.encode(body)); } catch (e) { return null; }
  if (!ok) return null;
  let obj;
  try { obj = JSON.parse(dec.decode(b64urlDecode(body))); } catch (e) { return null; }
  if (!obj || typeof obj.exp !== "number" || obj.exp * 1000 < Date.now()) return null;
  return obj;
}
