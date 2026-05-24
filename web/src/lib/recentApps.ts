const KEY = "review-dashboard.recent-apps";

export interface RecentApp {
  appId: number;
  country: string;
  lastVisitedAt: string;
}

export function getRecentApps(): RecentApp[] {
  if (typeof window === "undefined") return [];
  try {
    return (JSON.parse(localStorage.getItem(KEY) ?? "[]") as RecentApp[]) ?? [];
  } catch {
    return [];
  }
}

export function rememberApp(appId: number, country: string) {
  const existing = getRecentApps().filter(
    (a) => !(a.appId === appId && a.country === country),
  );
  const next: RecentApp[] = [
    { appId, country, lastVisitedAt: new Date().toISOString() },
    ...existing,
  ].slice(0, 6);
  localStorage.setItem(KEY, JSON.stringify(next));
}
