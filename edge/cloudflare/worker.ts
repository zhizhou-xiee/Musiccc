const MUSIC_ORIGIN = "https://musiccc-production.up.railway.app";

type FetchLike = (request: Request) => Promise<Response>;

function isMusicPath(pathname: string): boolean {
  return pathname === "/music" || pathname.startsWith("/music/");
}

export async function routeMusicRequest(
  request: Request,
  fetchRequest: FetchLike = fetch,
): Promise<Response> {
  const incomingUrl = new URL(request.url);
  if (!isMusicPath(incomingUrl.pathname)) return fetchRequest(request);

  const upstreamUrl = new URL(incomingUrl.pathname + incomingUrl.search, MUSIC_ORIGIN);
  const headers = new Headers(request.headers);
  headers.delete("host");
  headers.set("x-forwarded-host", incomingUrl.host);
  headers.set("x-forwarded-proto", incomingUrl.protocol.slice(0, -1));

  const init: RequestInit & { duplex?: "half" } = {
    method: request.method,
    headers,
    redirect: "manual",
  };
  if (request.method !== "GET" && request.method !== "HEAD") {
    init.body = request.body;
    init.duplex = "half";
  }

  return fetchRequest(new Request(upstreamUrl, init));
}

export default {
  fetch(request: Request): Promise<Response> {
    return routeMusicRequest(request);
  },
};
