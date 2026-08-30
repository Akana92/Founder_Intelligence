import { redirect } from "next/navigation";

import { adminRedirectUrl } from "@/lib/navigation";

const adminConsoleUrl =
  process.env.NEXT_PUBLIC_ADMIN_CONSOLE_URL ?? "http://127.0.0.1:8501/";

type AdminRedirectSearchParams = Promise<
  Readonly<Record<string, string | readonly string[] | undefined>>
>;

export default async function AdminRedirectPage({
  searchParams,
}: Readonly<{ searchParams: AdminRedirectSearchParams }>): Promise<never> {
  redirect(adminRedirectUrl(adminConsoleUrl, await searchParams));
}
