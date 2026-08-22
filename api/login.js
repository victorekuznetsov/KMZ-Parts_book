/* POST /api/login  { login, password } -> sets the HttpOnly session cookie.
   Verifies the password (PBKDF2) and, for temporary logins, that the account
   has not expired. Runs on the Vercel Edge runtime. */
export const config = { runtime: "edge" };

import accounts from "../auth/accounts.mjs";
import { verifyPassword, signToken, getSecret } from "../auth/token.mjs";

const COOKIE = "kmz_auth";
const SESSION_DAYS = 7;

function json(obj, status) {
  return new Response(JSON.stringify(obj), {
    status: status || 200,
    headers: { "content-type": "application/json", "cache-control": "no-store" }
  });
}

export default async function handler(request) {
  if (request.method !== "POST") return json({ error: "Метод не поддерживается" }, 405);
  let body;
  try { body = await request.json(); } catch (e) { return json({ error: "Некорректный запрос" }, 400); }
  const login = String(body && body.login || "").trim();
  const password = String(body && body.password || "");
  if (!login || !password) return json({ error: "Введите логин и пароль" }, 400);

  const user = (accounts.users || []).find(function (u) {
    return u.u.toLowerCase() === login.toLowerCase();
  });
  const ok = user ? await verifyPassword(password, user) : false;
  if (!user || !ok) return json({ error: "Неверный логин или пароль" }, 401);

  const now = Math.floor(Date.now() / 1000);
  let exp = now + SESSION_DAYS * 86400;
  if (user.role === "temporary") {
    if (!user.expires) return json({ error: "У временной учётки не задан срок" }, 403);
    const end = Math.floor(new Date(user.expires + "T23:59:59").getTime() / 1000);
    if (isNaN(end) || end < now) return json({ error: "Срок доступа истёк" }, 403);
    exp = Math.min(exp, end);
  }

  let secret;
  try { secret = getSecret(); }
  catch (e) { return json({ error: "Сервер не настроен: AUTH_SECRET не задан в Vercel" }, 500); }
  const token = await signToken({ u: user.u, r: user.role, exp: exp }, secret);
  const maxAge = Math.max(0, exp - now);
  const cookie = COOKIE + "=" + encodeURIComponent(token) +
    "; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=" + maxAge;
  return new Response(JSON.stringify({
    ok: true, user: user.name || user.u, role: user.role, expires: user.expires || null
  }), {
    status: 200,
    headers: { "content-type": "application/json", "cache-control": "no-store", "set-cookie": cookie }
  });
}
