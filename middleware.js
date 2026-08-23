/* Vercel Edge Middleware — закрывает весь каталог входом по логину и паролю.
   Без зависимостей: чтобы пропустить запрос дальше, возвращается ответ с
   заголовком `x-middleware-next` (его же отдаёт next() из @vercel/edge);
   иначе — редирект на /login.html. Страница входа, API авторизации и favicon
   остаются публичными. */
import { verifyToken, getSecret } from "./auth/token.mjs";

export const config = {
  matcher: ["/((?!api/login|api/logout|login\\.html|favicon\\.svg|robots\\.txt).*)"]
};

function cont() {
  return new Response(null, { headers: { "x-middleware-next": "1" } });
}

export default async function middleware(request) {
  const cookie = request.headers.get("cookie") || "";
  const m = cookie.match(/(?:^|;\s*)kmz_auth=([^;]+)/);
  const token = m ? decodeURIComponent(m[1]) : "";
  let claims = null;
  if (token) {
    try { claims = await verifyToken(token, getSecret()); }
    catch (e) { claims = null; } // AUTH_SECRET missing -> fail closed, fall through to login
  }
  if (claims) return cont();

  const url = new URL(request.url);
  const login = new URL("/login.html", request.url);
  login.searchParams.set("next", url.pathname + url.search);
  return Response.redirect(login, 302);
}
