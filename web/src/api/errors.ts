export type ApiError = { kind: "network" | "timeout" | "http" | "aborted"; status?: number; detail?: string; path: string; retryAfterS?: number };
export const isApiError = (error: unknown): error is ApiError => typeof error === "object" && error !== null && "kind" in error && "path" in error;
/** Worth asking again: the network or the server had a problem, or the server asked us to slow down. A 4xx answer
 *  (unknown stop, bad query) will not change, so it is not retried. */
export const isRetryable = (error: unknown) => !isApiError(error) || error.kind === "network" || error.kind === "timeout" || (error.kind === "http" && (error.status === 429 || (error.status ?? 0) >= 500));
