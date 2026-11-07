import { backendRequest, sameOrigin, tokenFrom, readJson, PayloadTooLarge } from "../../../../lib/session";

async function forward(request: Request, context: { params: Promise<{ path: string[] }> }): Promise<Response> {
  const { path } = await context.params;
  const route = path.join("/");
  const uuid = "[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}";
  const readable = new RegExp(`^(?:log-datasets|logs(?:/${uuid})?|investigations(?:/${uuid})?)$`);
  const writable = new RegExp(`^(?:search|investigations(?:/${uuid}/(?:approve|reject|retry|resume))?)$`);
  if (!(request.method === "GET" ? readable : writable).test(route)) {
    return Response.json({ detail: "Not found" }, { status: 404 });
  }
  if (request.method === "POST" && !sameOrigin(request)) {
    return Response.json({ detail: "Invalid origin" }, { status: 403 });
  }
  let body: unknown;
  if (request.method === "POST") {
    try { body = await readJson(request); } catch (error) {
      return Response.json({ detail: "Invalid request body" }, { status: error instanceof PayloadTooLarge ? 413 : 400 });
    }
  }
  const search = request.method === "GET" ? new URL(request.url).search : "";
  if (search.length > 3000) return Response.json({ detail: "Query too long" }, { status: 422 });
  return backendRequest(`/api/v1/${route}${search}`, request.method, tokenFrom(request), body);
}
export const GET = forward;
export const POST = forward;
