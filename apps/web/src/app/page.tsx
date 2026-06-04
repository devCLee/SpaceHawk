import MainPage from "./main/page";
import { Sgp4ConsoleLog } from "./Components/Sgp4ConsoleLog";
import AuthGuard from "./Components/guards/AuthGuard";

export default function Home() {
  return (
    <main>
      <Sgp4ConsoleLog />
      <AuthGuard>
        <MainPage />
      </AuthGuard>
    </main>
  );
}
