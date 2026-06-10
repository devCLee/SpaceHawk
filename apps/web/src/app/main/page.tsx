import DashboardShell from "../Components/DashboardShell";
import AlertToast from "../Components/AlertToast";

// The dashboard shell is static: the satellite catalog is no longer fetched
// here and prop-drilled into the client tree (that serialized ~4MB into the RSC
// document on every request and blocked first byte on the engine). The globe
// now fetches the catalog client-side via /api/catalog/all (see useCatalog),
// so this page streams immediately.
export default function MainPage() {
  return (
    <>
      <DashboardShell />
      <AlertToast />
    </>
  );
}
