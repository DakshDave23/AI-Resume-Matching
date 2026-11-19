import { useQuery } from "@tanstack/react-query";

import { getHealth } from "@/api/health";

/** The API's readiness: checked every 2 s until ready (the model loads at start-up), then every 30 s. */
export function useHealth() {
  return useQuery({
    queryKey: ["health"],
    queryFn: getHealth,
    retry: false,
    refetchInterval: (query) => (query.state.data?.status === "ok" ? 30_000 : 2_000),
  });
}
