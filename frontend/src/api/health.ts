import { request, type Schemas } from "@/api/client";

export type Health = Schemas["HealthResponse"];

/** 200 when ready, 503 while a dependency isn't: both carry the same body. */
export function getHealth(): Promise<Health> {
  return request<Health>("/health", { acceptStatuses: [503] });
}
