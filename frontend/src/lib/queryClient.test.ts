import { MutationObserver, QueryObserver } from "@tanstack/react-query";
import { toast } from "sonner";
import { beforeEach, expect, it, vi } from "vitest";

import { ApiError } from "@/api/client";
import { createQueryClient } from "@/lib/queryClient";

vi.mock("sonner", () => ({ toast: { error: vi.fn() } }));

beforeEach(() => vi.mocked(toast.error).mockClear());

it("toasts a failed action with the API's message", async () => {
  const client = createQueryClient();
  const observer = new MutationObserver(client, {
    mutationFn: () => Promise.reject(new ApiError(409, "busy", "Scoring is already running")),
  });
  await observer.mutate().catch(() => undefined);
  expect(toast.error).toHaveBeenCalledWith("Scoring is already running");
});

it("leaves a first load's error to the page, but toasts a failed refresh", async () => {
  const client = createQueryClient();
  client.setDefaultOptions({ queries: { retry: false } });
  const fail = () => Promise.reject(new Error("offline"));

  await client.fetchQuery({ queryKey: ["first"], queryFn: fail }).catch(() => undefined);
  expect(toast.error).not.toHaveBeenCalled();

  client.setQueryData(["shown"], { rows: [] });
  const observer = new QueryObserver(client, { queryKey: ["shown"], queryFn: fail });
  await observer.refetch();
  expect(toast.error).toHaveBeenCalledWith("Couldn't refresh the data.");
});
