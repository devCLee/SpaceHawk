"use client";

// App-wide client providers. TanStack Query backs the dashboard's BFF data
// fetching (catalog query/detail, conjunctions) so fetch state lives in the
// query cache instead of per-component effects.

import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Toaster } from "sonner";
import { AuthProvider } from "@/app/context/AuthContext";
import { GlobeControlsProvider } from "@/app/context/GlobeControlsContext";
import { AlertsProvider } from "@/app/context/AlertsContext";
import { CatalogViewProvider } from "@/app/context/CatalogViewContext";

export default function Providers({
  children,
}: {
  children: React.ReactNode;
}) {
  const [client] = React.useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: { staleTime: 30_000, refetchOnWindowFocus: false },
        },
      })
  );
  return (
    <QueryClientProvider client={client}>
      <AuthProvider>
        <GlobeControlsProvider>
          <AlertsProvider>
            {/* App-global so both the dashboard panels AND the Header's
                notification bell (rendered in the root layout, above the
                dashboard subtree) read the same watchlist/filter state. */}
            <CatalogViewProvider>
              {children}
              <Toaster theme="dark" position="top-center" richColors />
            </CatalogViewProvider>
          </AlertsProvider>
        </GlobeControlsProvider>
      </AuthProvider>
    </QueryClientProvider>
  );
}
