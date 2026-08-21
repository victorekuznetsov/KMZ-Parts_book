/* Vercel Edge Middleware — закрывает весь каталог входом по логину и паролю.
   Без зависимостей: чтобы пропустить запрос дальше, возвращается ответ с
   заголовком `x-middleware-next` (его же отдаёт next() из @vercel/edge);
   иначе — редирект на /login.html. Страница входа, API авторизации и favicon
   остаются публичными.

   Пока в auth/accounts.mjs НЕТ НИ ОДНОЙ учётки, вход не включается и сайт
   отдаётся всем: иначе свежий деплой невозможно было бы открыть. Как только
   заведена первая учётка (node build/make_user.mjs set …), доступ закрывается
   автоматически. Не оставляйте боевой каталог с пустым списком учёток. */
import { verifyToken, getSecret } from "./auth/token.mjs";
import accounts from "./auth/accounts.mjs";

export const config = {
  matcher: ["/((?!api/login|api/logout|login\\.html|favicon\\.svg|robots\\.txt).*)"]
};

function cont() {
  return new Response(null, { headers: { "x-middleware-next": "1" } });
}

export default async function middleware(request) {
  if (!(accounts.users || []).length) return cont();   // учётки ещё не заведены

  const cookie = request.headers.get("cookie") || "";
  const m = cookie.match(/(?:^|;\s*)kmz_auth=([^;]+)/);
  const token = m ? decodeURIComponent(m[1]) : "";
  const claims = token ? await verifyToken(token, getSecret()) : null;
  if (claims) return cont();

  const url = new URL(request.url);
  const login = new URL("/login.html", request.url);
  login.searchParams.set("next", url.pathname + url.search);
  return Response.redirect(login, 302);
}
