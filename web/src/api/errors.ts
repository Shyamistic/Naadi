export type ApiError = { kind: "network" | "timeout" | "http"; status?: number; detail?: string; path: string };
