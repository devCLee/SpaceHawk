"use client";

// App-wide client providers. TanStack Query backs the dashboard's BFF data
// fetching (catalog query/detail, conjunctions) so fetch state lives in the
// query cache instead of per-component effects.

import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Toaster } from "sonner";

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
      {children}
      <Toaster theme="dark" position="top-center" richColors />
    </QueryClientProvider>
  );
}
