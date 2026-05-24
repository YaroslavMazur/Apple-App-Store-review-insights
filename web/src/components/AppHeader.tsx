import { BarChart3 } from "lucide-react";
import { Link } from "react-router-dom";
import { ThemeToggle } from "./ThemeToggle";

export function AppHeader() {
  return (
    <header className="sticky top-0 z-40 w-full border-b bg-background/80 backdrop-blur">
      <div className="container flex h-16 items-center justify-between">
        <Link to="/" className="flex items-center gap-2 font-semibold">
          <BarChart3 className="h-5 w-5 text-primary" aria-hidden />
          <span>App Store Insights</span>
        </Link>
        <ThemeToggle />
      </div>
    </header>
  );
}
