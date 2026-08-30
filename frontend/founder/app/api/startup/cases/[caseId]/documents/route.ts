import { proxyFounderApi } from "@/lib/startup-proxy";

export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  return proxyFounderApi(request);
}
