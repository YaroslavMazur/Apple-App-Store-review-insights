import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ReactQueryDevtools } from "@tanstack/react-query-devtools";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { AppHeader } from "./components/AppHeader";
import { ThemeProvider } from "./lib/theme";
import { DashboardPage } from "./pages/DashboardPage";
import { HomePage } from "./pages/HomePage";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, refetchOnWindowFocus: false },
  },
});

export function App() {
  return (
    <ThemeProvider>
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <div className="min-h-screen bg-background text-foreground">
            <AppHeader />
            <main>
              <Routes>
                <Route path="/" element={<HomePage />} />
                <Route path="/app/:appId" element={<DashboardPage />} />
              </Routes>
            </main>
          </div>
          {import.meta.env.DEV && <ReactQueryDevtools initialIsOpen={false} />}
        </BrowserRouter>
      </QueryClientProvider>
    </ThemeProvider>
  );
}
