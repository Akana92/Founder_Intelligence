import { proxyFounderApi } from "@/lib/startup-proxy";

export const dynamic = "force-dynamic";

export async function GET(request: Request): Promise<Response> {
  return proxyFounderApi(request);
}
