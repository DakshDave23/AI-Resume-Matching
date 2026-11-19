import { ApiError } from "@/api/client";

/** The API's own message when there is one (it is written for the recruiter), else `fallback`. */
export function errorMessage(error: unknown, fallback = "Something went wrong."): string {
  return error instanceof ApiError ? error.message : fallback;
}
