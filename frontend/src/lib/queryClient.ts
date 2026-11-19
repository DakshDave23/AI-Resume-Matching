import { MutationCache, QueryCache, QueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { errorMessage } from "@/lib/errors";

/**
 * Errors become toasts (design doc §9): every failed action (save, upload, re-score), and a
 * failed background refresh of data already on screen. A page that can't load at all shows
 * its own error state instead, so it isn't reported twice.
 */
export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: { queries: { staleTime: 10_000, refetchOnWindowFocus: false } },
    mutationCache: new MutationCache({
      onError: (error) => {
        toast.error(errorMessage(error, "That didn't work. Please try again."));
      },
    }),
    queryCache: new QueryCache({
      onError: (error, query) => {
        if (query.state.data !== undefined) {
          toast.error(errorMessage(error, "Couldn't refresh the data."));
        }
      },
    }),
  });
}
