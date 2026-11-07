import { cookieName, sameOrigin } from "../../../../lib/session";

export async function POST(request: Request): Promise<Response> {
  if (!sameOrigin(request)) return Response.json({ detail: "Invalid origin" }, { status: 403 });
  return Response.json({ signed_in: false }, { headers: { "Cache-Control": "no-store",
    "Set-Cookie": `${cookieName}=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0` } });
}
