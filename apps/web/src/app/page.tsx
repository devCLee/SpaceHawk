import MainPage from "./main/page";
import { Sgp4ConsoleLog } from "./Components/Sgp4ConsoleLog";
import AuthGuard from "./Components/guards/AuthGuard";
import { t } from "@/lib/i18n/t";
import { SAMPLE_TLE } from "./data/sampleTle";

export default function Home() {
  return (
    <main>
      <h1 className="sr-only">{t("dashboard.srTitle")}</h1>
      <Sgp4ConsoleLog
        line1={SAMPLE_TLE.line1}
        line2={SAMPLE_TLE.line2}
        name={SAMPLE_TLE.name}
      />
      <AuthGuard>
        <MainPage />
      </AuthGuard>
    </main>
  );
}
