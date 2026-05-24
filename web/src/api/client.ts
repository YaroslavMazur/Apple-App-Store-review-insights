import type {
  ApiErrorEnvelope,
  CollectRequest,
  CollectResponse,
  InsightsResponse,
  MetricsResponse,
  RawReviewsResponse,
} from "./types";

const BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  code: string;
  status: number;
  details?: Record<string, unknown>;

  constructor(
    code: string,
    message: string,
    status: number,
    details?: Record<string, unknown>,
  ) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
    this.details = details;
  }
}

async function request<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "content-type": "application/json", ...init.headers },
    ...init,
  });
  if (!res.ok) {
    let body: ApiErrorEnvelope | { detail?: unknown } | undefined;
    try {
      body = await res.json();
    } catch {
      throw new ApiError("network", `HTTP ${res.status}`, res.status);
    }
    if (body && typeof body === "object" && "error" in body && body.error) {
      const e = body.error;
      throw new ApiError(
        e.code,
        e.message,
        res.status,
        e.details as Record<string, unknown> | undefined,
      );
    }
    throw new ApiError(
      "validation",
      `HTTP ${res.status}`,
      res.status,
      body as Record<string, unknown>,
    );
  }
  return res.json() as Promise<T>;
}

export const api = {
  collect(body: CollectRequest) {
    return request<CollectResponse>("/api/v1/reviews/collect", {
      method: "POST",
      body: JSON.stringify(body),
    });
  },
  metrics(appId: number, country: string) {
    return request<MetricsResponse>(
      `/api/v1/reviews/${appId}/metrics?country=${encodeURIComponent(country)}`,
    );
  },
  insights(appId: number, country: string) {
    return request<InsightsResponse>(
      `/api/v1/reviews/${appId}/insights?country=${encodeURIComponent(country)}`,
    );
  },
  reviews(appId: number, country: string) {
    return request<RawReviewsResponse>(
      `/api/v1/reviews/${appId}/raw?country=${encodeURIComponent(country)}`,
    );
  },
  csvUrl(appId: number, country: string) {
    return `${BASE}/api/v1/reviews/${appId}/raw?country=${encodeURIComponent(country)}&format=csv`;
  },
};
