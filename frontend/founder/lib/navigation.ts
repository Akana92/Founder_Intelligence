import { isFounderCaseId } from "./founder-case-storage.ts";

export type ProductSurface = "public_comparables" | "admin_console";

type SurfaceLink = Readonly<{
  href: string;
  external: boolean;
}>;

const surfaceLinks: Record<ProductSurface, SurfaceLink> = {
  public_comparables: { href: "/comparables", external: false },
  admin_console: { href: "/admin", external: false },
};

export function surfaceLinkFor(surface: ProductSurface): SurfaceLink {
  return surfaceLinks[surface];
}

type SearchParamValue = string | readonly string[] | undefined;

function normalizedCaseId(caseId: string | null | undefined): string | null {
  const normalized = caseId?.trim().toLowerCase() ?? "";
  return isFounderCaseId(normalized) ? normalized : null;
}

export function founderUrlForCase(currentHref: string, caseId: string): string {
  const normalized = normalizedCaseId(caseId);
  if (!normalized) return "/";

  const url = new URL(currentHref, "http://127.0.0.1:3000");
  url.searchParams.set("caseId", normalized);
  const query = url.searchParams.toString();
  return `${url.pathname}${query ? `?${query}` : ""}${url.hash}`;
}

export function adminConsoleLinkForCase(caseId: string | null | undefined): SurfaceLink {
  const normalized = normalizedCaseId(caseId);
  return {
    href: normalized ? `/admin?caseId=${encodeURIComponent(normalized)}` : "/admin",
    external: false,
  };
}

export function adminRedirectUrl(
  adminConsoleUrl: string,
  searchParams: Readonly<Record<string, SearchParamValue>>,
): string {
  const redirectUrl = new URL(adminConsoleUrl);
  const rawCaseId = searchParams.caseId;
  const caseId = normalizedCaseId(
    Array.isArray(rawCaseId) ? rawCaseId[0] : rawCaseId,
  );
  if (caseId) {
    redirectUrl.searchParams.set("caseId", caseId);
  }
  return redirectUrl.toString();
}
