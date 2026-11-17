import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { Overview, OverviewItem } from "./types";

/** Keyed under "summary" so every action that refreshes the dashboard summary refreshes this too. */
export const useOverview = () =>
  useQuery({ queryKey: ["summary", "overview"], queryFn: async () => (await api.get<Overview>("/dashboard/overview")).data });

/** Where a Today item leads: the application or the job it is about. */
export function itemLink(i: OverviewItem): string {
  if (i.application_id != null) return `/applied?app=${i.application_id}`;
  if (i.user_job_id != null) return `/discover?job=${i.user_job_id}`;
  return "/applied";
}
