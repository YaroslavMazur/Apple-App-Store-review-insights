import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import type { CollectRequest } from "../api/types";

const stale = 1000 * 60 * 5;

export function useMetrics(appId: number, country: string, enabled = true) {
  return useQuery({
    queryKey: ["metrics", appId, country],
    queryFn: () => api.metrics(appId, country),
    enabled: enabled && Number.isFinite(appId) && appId > 0,
    staleTime: stale,
  });
}

export function useInsights(appId: number, country: string, enabled = true) {
  return useQuery({
    queryKey: ["insights", appId, country],
    queryFn: () => api.insights(appId, country),
    enabled: enabled && Number.isFinite(appId) && appId > 0,
    staleTime: stale,
  });
}

export function useReviews(appId: number, country: string, enabled = true) {
  return useQuery({
    queryKey: ["reviews", appId, country],
    queryFn: () => api.reviews(appId, country),
    enabled: enabled && Number.isFinite(appId) && appId > 0,
    staleTime: stale,
  });
}

export function useCollect() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: CollectRequest) => api.collect(body),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ["metrics", data.app_id, data.country] });
      qc.invalidateQueries({
        queryKey: ["insights", data.app_id, data.country],
      });
      qc.invalidateQueries({ queryKey: ["reviews", data.app_id, data.country] });
    },
  });
}
