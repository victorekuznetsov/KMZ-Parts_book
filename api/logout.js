/* POST/GET /api/logout -> clears the session cookie. */
export const config = { runtime: "edge" };

export default async function handler() {
  const cookie = "kmz_auth=; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=0";
  return new Response(JSON.stringify({ ok: true }), {
    status: 200,
    headers: { "content-type": "application/json", "cache-control": "no-store", "set-cookie": cookie }
  });
}
