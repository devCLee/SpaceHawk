import MainPage from "./main/page";
import { Sgp4ConsoleLog } from "./Components/Sgp4ConsoleLog";
import AuthGuard from "./Components/guards/AuthGuard";
import { t } from "@/lib/i18n/t";
import mainData from "@/data/main.json";

export default function Home() {
  // Read the first catalog entry server-side and hand its TLE to the client
  // diagnostic as props — keeps the multi-MB catalog out of the client bundle.
  const first = mainData[0] as {
    TLE_LINE1?: string;
    TLE_LINE2?: string;
    OBJECT_NAME?: string;
  };
  return (
    <main>
      <h1 className="sr-only">{t("dashboard.srTitle")}</h1>
      <Sgp4ConsoleLog
        line1={first?.TLE_LINE1}
        line2={first?.TLE_LINE2}
        name={first?.OBJECT_NAME}
      />
      <AuthGuard>
        <MainPage />
      </AuthGuard>
    </main>
  );
}
