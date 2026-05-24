import { Link } from "react-router-dom";
import { ArrowRight, History } from "lucide-react";
import { AppSearchForm } from "../components/AppSearchForm";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import { getRecentApps } from "../lib/recentApps";

const COUNTRY_FLAGS: Record<string, string> = {
  us: "🇺🇸",
  gb: "🇬🇧",
  de: "🇩🇪",
  ua: "🇺🇦",
  fr: "🇫🇷",
};

export function HomePage() {
  const recent = getRecentApps();

  return (
    <div className="container py-10">
      <section className="mx-auto max-w-3xl">
        <h1 className="text-4xl font-bold tracking-tight md:text-5xl">
          Apple App Store review insights
        </h1>
        <p className="mt-3 text-lg text-muted-foreground">
          Enter an app id and country. We fetch the latest reviews, score
          sentiment, cluster the negatives into themes, and surface actionable
          insights for your product team.
        </p>

        <Card className="mt-8">
          <CardHeader>
            <CardTitle>Analyze an app</CardTitle>
            <CardDescription>
              Find the numeric id at <code className="rounded bg-muted px-1 py-0.5 text-xs">apps.apple.com/&hellip;/id&lt;APP_ID&gt;</code>.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <AppSearchForm />
          </CardContent>
        </Card>

        {recent.length > 0 && (
          <div className="mt-8">
            <div className="mb-3 flex items-center gap-2 text-sm font-medium text-muted-foreground">
              <History className="h-4 w-4" aria-hidden />
              Recently analyzed
            </div>
            <ul className="grid gap-2 sm:grid-cols-2">
              {recent.map((r) => (
                <li key={`${r.appId}-${r.country}`}>
                  <Link
                    to={`/app/${r.appId}?country=${r.country}`}
                    className="flex items-center justify-between rounded-md border bg-card px-4 py-3 text-sm transition-colors hover:bg-accent"
                  >
                    <span>
                      <span className="mr-2">
                        {COUNTRY_FLAGS[r.country] ?? r.country.toUpperCase()}
                      </span>
                      <span className="font-mono text-xs">{r.appId}</span>
                    </span>
                    <ArrowRight className="h-4 w-4 text-muted-foreground" aria-hidden />
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        )}
      </section>
    </div>
  );
}
