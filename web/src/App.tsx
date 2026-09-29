import { useCallback, useState } from "react";
import { AppProvider } from "./app-context";
import { Layout } from "./components/Layout";
import { Toast } from "./components/ui";
import { DashboardPage } from "./pages/Dashboard";
import { InboxPage } from "./pages/Inbox";
import { InvoicePage } from "./pages/Invoice";
import { QueuePage } from "./pages/Queue";
import { useRoute } from "./router";
import type { Batch } from "./types";

export function App({ batch }: { batch: Batch }) {
  return (
    <AppProvider batch={batch}>
      <Routes />
    </AppProvider>
  );
}

function Routes() {
  const route = useRoute();
  const [toast, setToast] = useState<string | null>(null);
  const clear = useCallback(() => setToast(null), []);
  return (
    <Layout route={route}>
      {route.page === "queue" && <QueuePage />}
      {route.page === "invoice" && <InvoicePage key={route.id} id={route.id} onToast={setToast} />}
      {route.page === "inbox" && <InboxPage onToast={setToast} />}
      {route.page === "dashboard" && <DashboardPage />}
      <Toast message={toast} onClear={clear} />
    </Layout>
  );
}
