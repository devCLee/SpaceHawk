import MainPage from "./main/page";
import { Sgp4ConsoleLog } from "./Components/Sgp4ConsoleLog";
import AuthGuard from "./Components/guards/AuthGuard";
import { t } from "@/lib/i18n/t";

export default function Home() {
  return (
    <main>
      <h1 className="sr-only">{t("dashboard.srTitle")}</h1>
      <Sgp4ConsoleLog />
      <AuthGuard>
        <MainPage />
      </AuthGuard>
    </main>
  );
}
