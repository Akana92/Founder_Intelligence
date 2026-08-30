import { parseApiError, type ApiErrorCode, type ApiFieldError } from "./contracts.ts";

export type StartupRouteMethod = "GET" | "POST";

export type StartupRouteManifestEntry = Readonly<{
  method: StartupRouteMethod;
  sameOriginPath: string;
}>;

export const startupRouteManifest: readonly StartupRouteManifestEntry[] = [
  { method: "POST", sameOriginPath: "/api/startup/cases" },
  { method: "GET", sameOriginPath: "/api/startup/cases/[caseId]" },
  { method: "POST", sameOriginPath: "/api/startup/cases/[caseId]/documents" },
  { method: "GET", sameOriginPath: "/api/startup/cases/[caseId]/analysis" },
  { method: "GET", sameOriginPath: "/api/startup/cases/[caseId]/profile" },
  { method: "GET", sameOriginPath: "/api/startup/cases/[caseId]/gtm" },
  { method: "GET", sameOriginPath: "/api/startup/cases/[caseId]/copilot/state" },
  { method: "GET", sameOriginPath: "/api/startup/cases/[caseId]/copilot/thread" },
  { method: "POST", sameOriginPath: "/api/startup/cases/[caseId]/copilot/messages" },
  { method: "POST", sameOriginPath: "/api/startup/cases/[caseId]/facts" },
  { method: "POST", sameOriginPath: "/api/startup/cases/[caseId]/assumptions" },
  { method: "GET", sameOriginPath: "/api/startup/cases/[caseId]/scenarios" },
  { method: "POST", sameOriginPath: "/api/startup/cases/[caseId]/scenarios/selection" },
  { method: "POST", sameOriginPath: "/api/startup/cases/[caseId]/research/plans" },
  { method: "POST", sameOriginPath: "/api/startup/cases/[caseId]/research/jobs" },
  {
    method: "GET",
    sameOriginPath: "/api/startup/cases/[caseId]/research/jobs/[jobId]",
  },
  { method: "GET", sameOriginPath: "/api/startup/cases/[caseId]/assets" },
  { method: "POST", sameOriginPath: "/api/startup/cases/[caseId]/assets" },
  { method: "GET", sameOriginPath: "/api/startup/cases/[caseId]/assets/[assetId]" },
  {
    method: "GET",
    sameOriginPath: "/api/startup/cases/[caseId]/assets/[assetId]/markdown",
  },
  {
    method: "GET",
    sameOriginPath: "/api/startup/cases/[caseId]/assets/[assetId]/provenance",
  },
  {
    method: "GET",
    sameOriginPath: "/api/startup/cases/[caseId]/assets/[assetId]/csv",
  },
  { method: "GET", sameOriginPath: "/api/startup/cases/[caseId]/advisor/next-question" },
  { method: "POST", sameOriginPath: "/api/startup/cases/[caseId]/advisor/answers" },
  { method: "GET", sameOriginPath: "/api/startup/cases/[caseId]/advisor/improvements" },
  {
    method: "POST",
    sameOriginPath:
      "/api/startup/cases/[caseId]/advisor/improvements/[proposalId]/decision",
  },
  { method: "GET", sameOriginPath: "/api/startup/cases/[caseId]/gate2/preview" },
  { method: "POST", sameOriginPath: "/api/startup/cases/[caseId]/gate2/decision" },
  { method: "POST", sameOriginPath: "/api/startup/cases/[caseId]/gate3/decision" },
  { method: "POST", sameOriginPath: "/api/startup/cases/[caseId]/gate4/decision" },
  { method: "GET", sameOriginPath: "/api/startup/cases/[caseId]/report" },
  { method: "GET", sameOriginPath: "/api/startup/cases/[caseId]/report/json" },
  { method: "GET", sameOriginPath: "/api/startup/cases/[caseId]/report/html" },
  { method: "GET", sameOriginPath: "/api/startup/cases/[caseId]/report/pdf" },
] as const;

export type FounderApiProxyFailureReason =
  | "api_unreachable"
  | "api_timeout"
  | "api_rejected"
  | "invalid_contract"
  | "unsafe_path";

export class FounderApiProxyError extends Error {
  readonly reason: FounderApiProxyFailureReason;

  constructor(reason: FounderApiProxyFailureReason, message: string) {
    super(message);
    this.name = "FounderApiProxyError";
    this.reason = reason;
  }
}

export type BuildStartupProxyRequestOptions = Readonly<{
  upstreamBaseUrl?: string;
  timeoutMs?: number;
}>;

export type StartupProxyRequest = Readonly<{
  url: string;
  init: RequestInit & { headers: Headers };
}>;

export type ProxyFounderApiOptions = BuildStartupProxyRequestOptions &
  Readonly<{
    fetcher?: typeof fetch;
  }>;

const DEFAULT_UPSTREAM_BASE_URL = "http://127.0.0.1:8000";
export const STARTUP_PROXY_REQUEST_TIMEOUT_MS = 55_000;
const REQUEST_ID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

const startupPatterns = [
  /^\/api\/startup\/cases$/,
  /^\/api\/startup\/cases\/[^/]+$/,
  /^\/api\/startup\/cases\/[^/]+\/documents$/,
  /^\/api\/startup\/cases\/[^/]+\/analysis$/,
  /^\/api\/startup\/cases\/[^/]+\/profile$/,
  /^\/api\/startup\/cases\/[^/]+\/gtm$/,
  /^\/api\/startup\/cases\/[^/]+\/copilot\/state$/,
  /^\/api\/startup\/cases\/[^/]+\/copilot\/thread$/,
  /^\/api\/startup\/cases\/[^/]+\/copilot\/messages$/,
  /^\/api\/startup\/cases\/[^/]+\/facts$/,
  /^\/api\/startup\/cases\/[^/]+\/assumptions$/,
  /^\/api\/startup\/cases\/[^/]+\/scenarios$/,
  /^\/api\/startup\/cases\/[^/]+\/scenarios\/selection$/,
  /^\/api\/startup\/cases\/[^/]+\/research\/plans$/,
  /^\/api\/startup\/cases\/[^/]+\/research\/jobs$/,
  /^\/api\/startup\/cases\/[^/]+\/research\/jobs\/[^/]+$/,
  /^\/api\/startup\/cases\/[^/]+\/assets$/,
  /^\/api\/startup\/cases\/[^/]+\/assets\/[^/]+$/,
  /^\/api\/startup\/cases\/[^/]+\/assets\/[^/]+\/markdown$/,
  /^\/api\/startup\/cases\/[^/]+\/assets\/[^/]+\/provenance$/,
  /^\/api\/startup\/cases\/[^/]+\/assets\/[^/]+\/csv$/,
  /^\/api\/startup\/cases\/[^/]+\/advisor\/next-question$/,
  /^\/api\/startup\/cases\/[^/]+\/advisor\/answers$/,
  /^\/api\/startup\/cases\/[^/]+\/advisor\/improvements$/,
  /^\/api\/startup\/cases\/[^/]+\/advisor\/improvements\/[^/]+\/decision$/,
  /^\/api\/startup\/cases\/[^/]+\/gate2\/preview$/,
  /^\/api\/startup\/cases\/[^/]+\/gate2\/decision$/,
  /^\/api\/startup\/cases\/[^/]+\/gate3\/decision$/,
  /^\/api\/startup\/cases\/[^/]+\/gate4\/decision$/,
  /^\/api\/startup\/cases\/[^/]+\/report$/,
  /^\/api\/startup\/cases\/[^/]+\/report\/json$/,
  /^\/api\/startup\/cases\/[^/]+\/report\/html$/,
  /^\/api\/startup\/cases\/[^/]+\/report\/pdf$/,
] as const;

function jsonError(
  code: ApiErrorCode,
  status: number,
  message: string,
  errors: readonly ApiFieldError[] = [],
): Response {
  return Response.json(
    errors.length > 0 ? { code, message, errors } : { code, message },
    {
      status,
      headers: { "Cache-Control": "no-store" },
    },
  );
}

function parsePath(pathOrUrl: string): string {
  if (!pathOrUrl.startsWith("/") || pathOrUrl.startsWith("//")) {
    throw new FounderApiProxyError("unsafe_path", "unsafe_path");
  }
  let pathname = pathOrUrl;
  try {
    pathname = new URL(pathOrUrl, "http://founder.local").pathname;
  } catch {
    throw new FounderApiProxyError("unsafe_path", "unsafe_path");
  }
  if (pathname.includes("\\") || pathname.includes("//")) {
    throw new FounderApiProxyError("unsafe_path", "unsafe_path");
  }
  rejectDecodedRouteConfusion(pathname);
  return pathname;
}

function rejectDecodedRouteConfusion(pathname: string): void {
  const rawSegmentCount = pathname.split("/").length;
  let decoded = pathname;
  for (let index = 0; index < 2; index += 1) {
    try {
      decoded = decodeURIComponent(decoded);
    } catch {
      throw new FounderApiProxyError("unsafe_path", "unsafe_path");
    }
    if (
      decoded.includes("\\") ||
      decoded.split("/").includes("..") ||
      decoded.split("/").length !== rawSegmentCount
    ) {
      throw new FounderApiProxyError("unsafe_path", "unsafe_path");
    }
  }
}

export function mapSameOriginStartupPath(pathOrUrl: string): string {
  const pathname = parsePath(pathOrUrl);
  if (pathname === "/api/capabilities") {
    return "/api/v1/product/capabilities";
  }
  if (
    !pathname.startsWith("/api/startup/") ||
    !startupPatterns.some((pattern) => pattern.test(pathname))
  ) {
    throw new FounderApiProxyError("unsafe_path", "unsafe_path");
  }
  return `/api/v1${pathname.slice("/api".length)}`;
}

function safeRequestId(value: string | null): string {
  if (value !== null && REQUEST_ID_PATTERN.test(value)) {
    return value.toLowerCase();
  }
  return globalThis.crypto.randomUUID();
}

function safeUpstreamBaseUrl(value: string | undefined): URL {
  let parsed: URL;
  try {
    parsed = new URL(value ?? DEFAULT_UPSTREAM_BASE_URL);
  } catch {
    throw new FounderApiProxyError("invalid_contract", "Founder API base URL is invalid");
  }
  if (!["http:", "https:"].includes(parsed.protocol)) {
    throw new FounderApiProxyError("invalid_contract", "Founder API base URL is invalid");
  }
  parsed.pathname = parsed.pathname.replace(/\/+$/, "");
  parsed.search = "";
  parsed.hash = "";
  return parsed;
}

function copySafeRequestHeaders(request: Request): Headers {
  const headers = new Headers();
  const accept = request.headers.get("accept");
  if (accept !== null) {
    headers.set("accept", accept);
  }
  const contentType = request.headers.get("content-type");
  if (contentType !== null && !contentType.toLowerCase().startsWith("multipart/form-data")) {
    headers.set("content-type", contentType);
  }
  headers.set("x-request-id", safeRequestId(request.headers.get("x-request-id")));
  return headers;
}

async function copyRequestBody(request: Request): Promise<BodyInit | null> {
  if (request.method === "GET" || request.method === "HEAD") {
    return null;
  }
  const contentType = request.headers.get("content-type")?.toLowerCase() ?? "";
  if (contentType.startsWith("multipart/form-data")) {
    return request.clone().formData();
  }
  return request.clone().text();
}

export async function buildStartupProxyRequest(
  request: Request,
  options: BuildStartupProxyRequestOptions = {},
): Promise<StartupProxyRequest> {
  const requestUrl = new URL(request.url);
  const upstreamBase = safeUpstreamBaseUrl(
    options.upstreamBaseUrl ?? process.env.FOUNDER_API_BASE_URL,
  );
  const upstreamPath = mapSameOriginStartupPath(requestUrl.pathname);
  const upstreamUrl = new URL(upstreamPath, upstreamBase);
  upstreamUrl.search = requestUrl.search;

  const init: RequestInit & { headers: Headers } = {
    method: request.method,
    headers: copySafeRequestHeaders(request),
    cache: "no-store",
    signal: AbortSignal.timeout(
      options.timeoutMs ?? STARTUP_PROXY_REQUEST_TIMEOUT_MS,
    ),
  };
  const body = await copyRequestBody(request);
  if (body !== null) {
    init.body = body;
  }
  return { url: upstreamUrl.toString(), init };
}

function copySafeResponseHeaders(upstream: Response): Headers {
  const headers = new Headers({ "Cache-Control": "no-store" });
  const contentType = upstream.headers.get("content-type");
  if (contentType !== null) {
    const normalized = contentType.toLowerCase();
    if (
      normalized.startsWith("application/json") ||
      normalized.startsWith("text/html") ||
      normalized.startsWith("application/pdf") ||
      normalized.startsWith("text/plain") ||
      normalized.startsWith("text/markdown") ||
      normalized.startsWith("text/csv")
    ) {
      headers.set("content-type", contentType);
    }
  }
  const contentDisposition = upstream.headers.get("content-disposition");
  if (contentDisposition !== null && safeAttachmentDisposition(contentDisposition)) {
    headers.set("content-disposition", contentDisposition);
  }
  return headers;
}

function safeAttachmentDisposition(value: string): boolean {
  return /^attachment;\s*filename="[A-Za-z0-9._-]{1,180}"$/u.test(value);
}

function mapProxyError(error: unknown): Response {
  if (error instanceof FounderApiProxyError) {
    const status = error.reason === "unsafe_path" ? 400 : 503;
    return jsonError(error.reason, status, safeMessage(error.reason));
  }
  if (error instanceof DOMException && ["AbortError", "TimeoutError"].includes(error.name)) {
    return jsonError("api_timeout", 504, safeMessage("api_timeout"));
  }
  return jsonError("api_unreachable", 503, safeMessage("api_unreachable"));
}

function safeMessage(reason: FounderApiProxyFailureReason): string {
  if (reason === "unsafe_path") {
    return "Startup API path is not allowed";
  }
  if (reason === "api_timeout") {
    return "Founder API request timed out";
  }
  if (reason === "api_rejected") {
    return "Founder API request was rejected";
  }
  if (reason === "invalid_contract") {
    return "Founder API contract is invalid";
  }
  return "Founder API could not be reached";
}

export async function proxyFounderApi(
  request: Request,
  options: ProxyFounderApiOptions = {},
): Promise<Response> {
  let upstreamRequest: StartupProxyRequest;
  try {
    upstreamRequest = await buildStartupProxyRequest(request, options);
  } catch (error) {
    return mapProxyError(error);
  }

  try {
    const upstream = await (options.fetcher ?? fetch)(
      upstreamRequest.url,
      upstreamRequest.init,
    );
    if (!upstream.ok) {
      const body = await upstream
        .clone()
        .json()
        .then((value: unknown) => parseApiError(value))
        .catch(() => null);
      if (body !== null) {
        return jsonError(body.code, upstream.status, body.message, body.errors ?? []);
      }
      return jsonError("api_rejected", 502, safeMessage("api_rejected"));
    }
    return new Response(upstream.body, {
      status: upstream.status,
      statusText: upstream.statusText,
      headers: copySafeResponseHeaders(upstream),
    });
  } catch (error) {
    return mapProxyError(error);
  }
}
