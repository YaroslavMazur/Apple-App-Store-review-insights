import { zodResolver } from "@hookform/resolvers/zod";
import { Loader2, Search } from "lucide-react";
import { useForm } from "react-hook-form";
import { useNavigate } from "react-router-dom";
import { z } from "zod";
import { useCollectStream } from "../hooks/useCollectStream";
import { rememberApp } from "../lib/recentApps";
import { StageList } from "./StageList";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { Select } from "./ui/select";

const COUNTRY_OPTIONS: { code: string; label: string }[] = [
  { code: "us", label: "🇺🇸 United States" },
  { code: "gb", label: "🇬🇧 United Kingdom" },
  { code: "de", label: "🇩🇪 Germany" },
  { code: "fr", label: "🇫🇷 France" },
  { code: "es", label: "🇪🇸 Spain" },
  { code: "it", label: "🇮🇹 Italy" },
  { code: "nl", label: "🇳🇱 Netherlands" },
  { code: "pl", label: "🇵🇱 Poland" },
  { code: "ua", label: "🇺🇦 Ukraine" },
  { code: "ca", label: "🇨🇦 Canada" },
  { code: "au", label: "🇦🇺 Australia" },
  { code: "br", label: "🇧🇷 Brazil" },
  { code: "mx", label: "🇲🇽 Mexico" },
  { code: "jp", label: "🇯🇵 Japan" },
  { code: "kr", label: "🇰🇷 South Korea" },
  { code: "cn", label: "🇨🇳 China" },
  { code: "in", label: "🇮🇳 India" },
];

const COUNTRY_CODES = COUNTRY_OPTIONS.map((o) => o.code) as [string, ...string[]];

const schema = z.object({
  appId: z.coerce
    .number({ message: "App ID must be a number" })
    .int()
    .positive("App ID must be a positive integer"),
  country: z.enum(COUNTRY_CODES, { message: "Pick a country" }),
  limit: z.coerce.number().int().min(1).max(5000).default(100),
});

type FormValues = z.input<typeof schema>;

export function AppSearchForm() {
  const navigate = useNavigate();
  const collect = useCollectStream();
  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { appId: 324684580, country: "us", limit: 100 } as FormValues,
  });

  const onSubmit = async (raw: FormValues) => {
    const parsed = schema.parse(raw);
    const result = await collect.start({
      app_id: parsed.appId,
      country: parsed.country,
      limit: parsed.limit,
    });
    if (result) {
      rememberApp(parsed.appId, parsed.country);
      navigate(`/app/${parsed.appId}?country=${parsed.country}`);
    }
  };

  return (
    <div className="space-y-4">
      <form
        onSubmit={form.handleSubmit(onSubmit)}
        className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-end"
      >
        <div className="flex-1 min-w-[180px]">
          <label
            htmlFor="appId"
            className="mb-1.5 block text-sm font-medium"
          >
            App ID
          </label>
          <Input
            id="appId"
            type="number"
            inputMode="numeric"
            placeholder="324684580"
            disabled={collect.isPending}
            {...form.register("appId")}
          />
          {form.formState.errors.appId && (
            <p className="mt-1 text-xs text-destructive">
              {form.formState.errors.appId.message}
            </p>
          )}
        </div>

        <div className="w-full sm:w-48">
          <label htmlFor="country" className="mb-1.5 block text-sm font-medium">
            Country
          </label>
          <Select
            id="country"
            disabled={collect.isPending}
            {...form.register("country")}
          >
            {COUNTRY_OPTIONS.map((o) => (
              <option key={o.code} value={o.code}>
                {o.label}
              </option>
            ))}
          </Select>
          {form.formState.errors.country && (
            <p className="mt-1 text-xs text-destructive">
              {form.formState.errors.country.message}
            </p>
          )}
        </div>

        <div className="w-full sm:w-32">
          <label htmlFor="limit" className="mb-1.5 block text-sm font-medium">
            Sample size
          </label>
          <Input
            id="limit"
            type="number"
            min={1}
            max={5000}
            disabled={collect.isPending}
            {...form.register("limit")}
          />
          <p className="mt-1 text-xs text-muted-foreground">
            Random reviews to analyze
          </p>
        </div>

        <Button
          type="submit"
          disabled={collect.isPending}
          className="w-full sm:w-auto"
        >
          {collect.isPending ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
              Analyzing…
            </>
          ) : (
            <>
              <Search className="h-4 w-4" aria-hidden />
              Analyze
            </>
          )}
        </Button>
      </form>

      {collect.error && (
        <p
          className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive"
          role="alert"
        >
          {collect.error.message}
        </p>
      )}

      {(collect.isPending || collect.data) && (
        <div className="rounded-lg border bg-muted/40 p-4">
          <div className="mb-2 flex items-center justify-between text-xs uppercase tracking-wide text-muted-foreground">
            <span>Pipeline progress</span>
          </div>
          <StageList stages={collect.stages} />
        </div>
      )}
    </div>
  );
}
