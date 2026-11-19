import { afterEach, describe, expect, it, vi } from "vitest";

import { API_BASE_URL, ApiError, request } from "@/api/client";
import { getHealth } from "@/api/health";

function respond(status: number, body: unknown, statusText = ""): void {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () =>
      body === undefined
        ? new Response(null, { status, statusText })
        : new Response(typeof body === "string" ? body : JSON.stringify(body), {
            status,
            statusText,
            headers: { "Content-Type": "application/json" },
          }),
    ),
  );
}

async function caught(promise: Promise<unknown>): Promise<ApiError> {
  try {
    await promise;
  } catch (error) {
    if (error instanceof ApiError) return error;
    throw error;
  }
  throw new Error("expected the request to fail");
}

afterEach(() => vi.unstubAllGlobals());

describe("request", () => {
  it("calls the API base URL and returns the JSON body", async () => {
    respond(200, { id: "42" });
    await expect(request<{ id: string }>("/jobs/42")).resolves.toEqual({ id: "42" });
    expect(fetch).toHaveBeenCalledWith(
      `${API_BASE_URL}/jobs/42`,
      expect.objectContaining({ headers: expect.objectContaining({ Accept: "application/json" }) }),
    );
  });

  it("returns undefined for 204 No Content", async () => {
    respond(204, undefined);
    await expect(request("/jobs/42", { method: "DELETE" })).resolves.toBeUndefined();
  });

  it("turns the backend's error envelope into an ApiError", async () => {
    respond(404, { error: { code: "not_found", message: "Job not found", details: null } });
    const error = await caught(request("/jobs/missing"));
    expect([error.status, error.code, error.message]).toEqual([404, "not_found", "Job not found"]);
  });

  it("keeps validation details", async () => {
    const details = [{ loc: ["body", "text"], msg: "Field required" }];
    respond(422, {
      error: { code: "validation_error", message: "Request validation failed", details },
    });
    expect((await caught(request("/jobs", { method: "POST" }))).details).toEqual(details);
  });

  it("copes with an error that isn't the envelope", async () => {
    respond(502, "<html>Bad gateway</html>", "Bad Gateway");
    const error = await caught(request("/jobs"));
    expect([error.status, error.code, error.message]).toEqual([502, "http_error", "Bad Gateway"]);
  });

  it("reports an unreachable API as status 0", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new TypeError("Failed to fetch");
      }),
    );
    const error = await caught(request("/health"));
    expect([error.status, error.code]).toEqual([0, "network_error"]);
    expect(error.message).toContain("backend running");
  });
});

describe("getHealth", () => {
  it("reads the body of a 503 instead of failing: the model may still be loading", async () => {
    const loading = {
      status: "degraded",
      version: "0.1.0",
      environment: "development",
      checks: { database: "ok", pgvector: "0.8.7", embedding_model: "loading" },
    };
    respond(503, loading);
    await expect(getHealth()).resolves.toEqual(loading);
  });
});
