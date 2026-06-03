import CesiumWrapper from "../Components/CesiumWrapper";
import mainData from "@/data/main.json";
import type { TleObject } from "../utils/sgp4FromTle";

const tleEntries = mainData.filter(
  (e: { TLE_LINE1?: string; TLE_LINE2?: string }) => e.TLE_LINE1 && e.TLE_LINE2
) as TleObject[]; 

export default function MainPage() {
  return (
    <CesiumWrapper
      positions={[]}
      tleEntries={tleEntries}
    />
  );
}
