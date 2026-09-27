export default {
  async fetch(request, env) {
    const requested = new URL(request.url);
    if (["/pdf-viewer", "/pdf-viewer/", "/print-slip", "/print-slip/"].includes(requested.pathname)) {
      requested.pathname = requested.pathname.startsWith("/print-slip") ? "/print-slip/" : "/pdf-viewer/";
      return env.ASSETS.fetch(new Request(requested, request));
    }
    const lastSegment = requested.pathname.split("/").pop() || "";
    if (request.method === "GET" && requested.pathname !== "/" && !lastSegment.includes(".")) {
      requested.pathname = "/";
      return env.ASSETS.fetch(new Request(requested, request));
    }

    const response = await env.ASSETS.fetch(request);
    if (response.status !== 404 || request.method !== "GET") return response;

    const url = new URL(request.url);
    url.pathname = "/";
    return env.ASSETS.fetch(new Request(url, request));
  },
};
