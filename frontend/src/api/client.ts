/**
 * The one HTTP client for the backend API (design doc §9, data layer).
 *
 * Every error comes back as an ApiError carrying the backend's error envelope
 * ({"error": {"code", "message", "details"}}), so pages can show `message` as-is.
 */
import type { components } from "@/types/api";

/** Request and response bodies, generated from the backend's OpenAPI schema. */
export type Schemas = components["schemas"];

const DEFAULT_BASE_URL = "http://localhost:8000/api/v1";

export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || DEFAULT_BASE_URL).replace(
  /\/+$/,
  "",
);

export class ApiError extends Error {
  readonly status: number; // 0 when the API couldn't be reached at all
  readonly code: string;
  readonly details: unknown;

  constructor(status: number, code: string, message: string, details: unknown = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

interface ErrorEnvelope {
  error: { code: string; message: string; details: unknown };
}

function isErrorEnvelope(body: unknown): body is ErrorEnvelope {
  if (typeof body !== "object" || body === null || !("error" in body)) return false;
  const error = (body as { error: unknown }).error;
  return typeof error === "object" && error !== null && "code" in error && "message" in error;
}

export interface RequestOptions extends RequestInit {
  /** Non-2xx statuses whose body is still a normal response (e.g. /health's 503). */
  acceptStatuses?: number[];
}

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { acceptStatuses = [], headers, ...init } = options;
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers: { Accept: "application/json", ...headers },
    });
  } catch {
    throw new ApiError(0, "network_error", "Can't reach the API. Is the backend running?");
  }

  if (response.ok || acceptStatuses.includes(response.status)) {
    if (response.status === 204) return undefined as T;
    return (await response.json()) as T;
  }

  const body: unknown = await response.json().catch(() => null);
  if (isErrorEnvelope(body)) {
    const { code, message, details } = body.error;
    throw new ApiError(response.status, code, message, details);
  }
  throw new ApiError(response.status, "http_error", response.statusText || "Request failed");
}
