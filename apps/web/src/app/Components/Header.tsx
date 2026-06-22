"use client";

// Unified top-right control bar (SpaceHawk Top-Right Redesign v2). One coherent
// toolbar replaces the three colliding floating widgets the app used to stack by
// magic offsets — the globe online/offline switch (top:8), Cesium's scene-mode +
// imagery picker (top:48), and the notification bell (top:152):
//
//   wordmark | 라이브 · 샌드박스 · 감사 로그 | ◐ scene · ▦ imagery · ● 지구본 온라인 | 🔔 | 계정
//
// The globe-view group + bell only appear on the dashboard (when a Cesium viewer
// is registered with GlobeControls); the workspace modes + account chip show on
// every page. Because the persistent controls live in the header, they never
// overlap the satellite info panel again.

import React from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/app/context/AuthContext";
import { useGlobeControls } from "@/app/context/GlobeControlsContext";
import {
  useAlerts,
  accentFor,
  titleFor,
  TIME_WINDOWS,
} from "@/app/context/AlertsContext";
import { http } from "@/lib/api/apiClient";
import { t } from "@/lib/i18n/t";

type ModeId = "live" | "sandbox" | "audit";
type Pop = "alerts" | "account" | null;

export default function Header() {
  const { user, isAdmin, refresh } = useAuth();
  const router = useRouter();
  const globe = useGlobeControls();
  const { history } = useAlerts();

  const [mode, setActiveMode] = React.useState<ModeId>("live");
  const [pop, setPop] = React.useState<Pop>(null);
  const clusterRef = React.useRef<HTMLDivElement>(null);
  const imageryBtnRef = React.useRef<HTMLButtonElement>(null);

  async function signOut() {
    try {
      await http.post("/api/auth/logout");
    } finally {
      refresh();
      router.replace("/signin");
    }
  }

  // Close the alerts/account popovers on any click outside the right cluster.
  React.useEffect(() => {
    if (pop === null) return;
    function onDown(e: PointerEvent) {
      if (!clusterRef.current?.contains(e.target as Node)) setPop(null);
    }
    document.addEventListener("pointerdown", onDown);
    return () => document.removeEventListener("pointerdown", onDown);
  }, [pop]);

  // Dismiss the imagery dropdown on any click outside it and its toggle button.
  // The panel is Cesium's curated BaseLayerPicker (floated under the header by
  // globals.css); GlobeControls strips Cesium's own auto-close so the Header is
  // its single owner. Capture phase so we run before the click lands. Clicks on
  // the button fall through to its onClick toggle; clicks inside the panel
  // (picking a basemap) keep it open.
  React.useEffect(() => {
    if (!globe.imageryOpen) return;
    function onDown(e: PointerEvent) {
      const target = e.target as Element | null;
      if (imageryBtnRef.current?.contains(target as Node)) return;
      if (target?.closest?.(".cesium-baseLayerPicker-dropDown")) return;
      globe.toggleImagery();
    }
    document.addEventListener("pointerdown", onDown, true);
    return () => document.removeEventListener("pointerdown", onDown, true);
  }, [globe]);

  // A header popover and the imagery dropdown are mutually exclusive. Opening a
  // popover counts as a click outside the panel, so its own outside-dismiss
  // (above) closes it; opening imagery clears any popover below.
  function openPop(next: Pop) {
    setPop((cur) => (cur === next ? null : next));
  }
  function openImagery() {
    setPop(null);
    if (globe.imageryAvailable) globe.toggleImagery();
  }

  function selectMode(id: ModeId) {
    setActiveMode(id);
    if (id === "audit") router.push("/admin/audit");
  }

  const online = globe.mode === "online";

  return (
    <header className="sh-hdr">
      <style>{HEADER_CSS}</style>

      <div className="left">
        {globe.active && (
          <button
            className={`icon-btn rail-btn${globe.railOpen ? " active" : ""}`}
            onClick={globe.toggleRail}
            title={globe.railOpen ? t("header.railHide") : t("header.railShow")}
            aria-label={globe.railOpen ? t("header.railHide") : t("header.railShow")}
            aria-pressed={globe.railOpen}
          >
            <PanelLeftIcon />
          </button>
        )}
        <div className="wordmark">SpaceHawk</div>
      </div>

      <div className="right" ref={clusterRef}>
        {/* workspace modes */}
        <div className="seg" role="group" aria-label={t("header.modesAria")}>
          <button
            className={mode === "live" ? "on" : ""}
            onClick={() => selectMode("live")}
          >
            {t("header.live")}
          </button>
          <button
            className={mode === "sandbox" ? "on" : ""}
            onClick={() => selectMode("sandbox")}
          >
            {t("header.sandbox")}
          </button>
          {isAdmin && (
            <button
              className={mode === "audit" ? "on" : ""}
              onClick={() => selectMode("audit")}
            >
              {t("header.audit")}
            </button>
          )}
        </div>

        {/* globe-view group — dashboard only */}
        {globe.active && (
          <>
            <span className="divider" />
            <div className="group">
              <div
                className="scene-seg"
                role="group"
                aria-label={t("globe.scene.aria")}
              >
                <button
                  className={globe.sceneMode === "3D" ? "on" : ""}
                  onClick={() => globe.setSceneMode("3D")}
                  title={t("globe.scene.3d")}
                  aria-label={t("globe.scene.3d")}
                >
                  <SceneIcon3D />
                </button>
                <button
                  className={globe.sceneMode === "2D" ? "on" : ""}
                  onClick={() => globe.setSceneMode("2D")}
                  title={t("globe.scene.2d")}
                  aria-label={t("globe.scene.2d")}
                >
                  <SceneIcon2D />
                </button>
                <button
                  className={globe.sceneMode === "Columbus" ? "on" : ""}
                  onClick={() => globe.setSceneMode("Columbus")}
                  title={t("globe.scene.columbus")}
                  aria-label={t("globe.scene.columbus")}
                >
                  <SceneIconColumbus />
                </button>
              </div>

              <button
                ref={imageryBtnRef}
                className={`icon-btn${globe.imageryOpen ? " active" : ""}`}
                onClick={openImagery}
                disabled={!globe.imageryAvailable}
                title={
                  globe.imageryAvailable
                    ? t("globe.imagery.title")
                    : t("globe.imagery.unavailable")
                }
                aria-label={t("globe.imagery.title")}
              >
                <ImageryIcon />
                <ChevronIcon className="chev" />
              </button>

              <button
                className={`online${online ? "" : " off"}`}
                onClick={() => globe.setMode(online ? "offline" : "online")}
                title={online ? t("globe.tooltip.online") : t("globe.tooltip.offline")}
                aria-label={t("globe.toggleAria")}
                aria-pressed={online}
              >
                <span className="dot" />
                <span className="lbl">
                  {t("globe.label.prefix")}{" "}
                  <b>{online ? t("globe.state.online") : t("globe.state.offline")}</b>
                  {online ? " · Ion" : ""}
                </span>
                <span className={`switch${online ? " on" : ""}`} />
              </button>
            </div>

            <button
              className="icon-btn bell-btn"
              onClick={() => openPop("alerts")}
              title={t("notifications.title")}
              aria-label={t("notifications.title")}
              aria-expanded={pop === "alerts"}
            >
              <BellIcon />
              {history.length > 0 && (
                <span className="badge">
                  {history.length > 99 ? "99+" : history.length}
                </span>
              )}
            </button>
          </>
        )}

        {/* account */}
        {user && (
          <>
            <span className="divider" />
            <button
              className="chip"
              onClick={() => openPop("account")}
              aria-label={t("header.accountMenu")}
              aria-expanded={pop === "account"}
            >
              <span className="avatar">
                {user.username.charAt(0).toUpperCase()}
              </span>
              <span className="who">
                <b>{user.username}</b>
                <span>{user.role}</span>
              </span>
              <ChevronIcon className="chev" />
            </button>
          </>
        )}

        {/* alerts dropdown */}
        {pop === "alerts" && <AlertsPop history={history} />}

        {/* account dropdown */}
        {pop === "account" && user && (
          <div className="pop pop-account open">
            <div className="acc-head">
              <span className="avatar">
                {user.username.charAt(0).toUpperCase()}
              </span>
              <div>
                <b>{user.username}</b>
                <span>{user.role}</span>
              </div>
            </div>
            {isAdmin && (
              <a href="/admin/audit">
                <AuditIcon /> {t("header.audit")}
              </a>
            )}
            <div className="sep" />
            <button className="danger" onClick={signOut}>
              <SignOutIcon /> {t("header.signOut")}
            </button>
          </div>
        )}
      </div>
    </header>
  );
}

/** Notifications dropdown — the session alert history with a time-window filter.
 * Read-only: durable triage of conjunction alerts lives in the AlertCenter
 * panel, so the rows here are a heads-up surface, not action buttons. */
function AlertsPop({ history }: { history: ReturnType<typeof useAlerts>["history"] }) {
  const [windowMs, setWindowMs] = React.useState(TIME_WINDOWS[2].ms); // 1h
  // Snapshot the clock in an effect (Date.now() is impure in render) and tick it
  // once a second so a "1m" view drops entries as they age out.
  const [now, setNow] = React.useState(() => Date.now());
  React.useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, []);
  const filtered = history.filter((r) => now - r.receivedAt <= windowMs);

  return (
    <div className="pop pop-alerts open">
      <div className="pop-head">
        <h3>{t("notifications.title")}</h3>
        <span className="sub">{t("notifications.subtitle")}</span>
      </div>
      <div className="filters">
        {TIME_WINDOWS.map((w) => (
          <button
            key={w.label}
            className={w.ms === windowMs ? "on" : ""}
            onClick={() => setWindowMs(w.ms)}
          >
            {w.label}
          </button>
        ))}
      </div>
      {filtered.length === 0 ? (
        <p className="alerts-empty">{t("notifications.empty")}</p>
      ) : (
        filtered.map((r) => (
          <div className="alert-row" key={r.id}>
            <div className="top">
              <span className="sev" style={{ color: accentFor(r.alert) }}>
                {titleFor(r.alert)}
              </span>
              <span className="time">
                {new Date(r.receivedAt).toLocaleTimeString("ko-KR")}
              </span>
            </div>
            <div className="msg">{r.alert.message}</div>
          </div>
        ))
      )}
    </div>
  );
}

/* ---- icons (match the design's stroke set) ---- */
// lucide `panel-left` — the analyst-rail toggle.
function PanelLeftIcon() {
  return (
    <svg
      className="icon"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <rect x="3" y="3" width="18" height="18" rx="2" />
      <path d="M9 3v18" />
    </svg>
  );
}
function SceneIcon3D() {
  return (
    <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6">
      <circle cx="12" cy="12" r="9" />
      <path d="M3 12h18M12 3c2.6 2.5 2.6 16 0 18M12 3c-2.6 2.5-2.6 16 0 18" />
    </svg>
  );
}
function SceneIcon2D() {
  return (
    <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6">
      <rect x="4" y="5" width="16" height="14" rx="1" />
      <path d="M4 9.7h16M4 14.3h16M9.3 5v14M14.7 5v14" />
    </svg>
  );
}
function SceneIconColumbus() {
  return (
    <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6">
      <path d="M2 19h20L16.5 6.5h-9L2 19z" />
      <path d="M4.8 13.6h14.4M6.6 9.6h10.8M12 6.5v12.5" />
    </svg>
  );
}
function ImageryIcon() {
  return (
    <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7">
      <path d="M12 3l9 5-9 5-9-5 9-5z" />
      <path d="M3 13l9 5 9-5" />
    </svg>
  );
}
function ChevronIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M6 9l6 6 6-6" />
    </svg>
  );
}
function BellIcon() {
  return (
    <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7">
      <path d="M18 8a6 6 0 1 0-12 0c0 7-3 9-3 9h18s-3-2-3-9" />
      <path d="M13.7 21a2 2 0 0 1-3.4 0" />
    </svg>
  );
}
function AuditIcon() {
  return (
    <svg className="mi" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M9 5H7a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-2" />
      <rect x="9" y="3" width="6" height="4" rx="1" />
      <path d="M9 13h6M9 17h4" />
    </svg>
  );
}
function SignOutIcon() {
  return (
    <svg className="mi" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
      <path d="M16 17l5-5-5-5M21 12H9" />
    </svg>
  );
}

// Scoped to `.sh-hdr` so the design's generic class names can't leak. Tokens are
// inlined from the prototype's :root (panel rgba(8,12,20,.92), sky-500 accent,
// hairlines), matching the app's dark operational theme.
const HEADER_CSS = `
.sh-hdr{position:fixed;top:0;left:0;right:0;height:56px;z-index:50;
  display:flex;align-items:center;justify-content:space-between;padding:0 16px;
  background:rgba(0,0,0,0.78);border-bottom:1px solid rgba(255,255,255,0.08);
  color:#e6edf3;font-family:inherit;-webkit-font-smoothing:antialiased}
.sh-hdr .left{display:flex;align-items:center;gap:10px}
.sh-hdr .wordmark{font-size:14px;font-weight:650;letter-spacing:.02em}
.sh-hdr .right{display:flex;align-items:center;gap:12px;position:relative}
.sh-hdr .divider{width:1px;height:22px;background:rgba(255,255,255,0.12);flex:none}

.sh-hdr .seg{display:flex;background:rgba(255,255,255,0.05);
  border:1px solid rgba(255,255,255,0.12);border-radius:8px;padding:3px;gap:2px}
.sh-hdr .seg button{appearance:none;border:0;background:transparent;color:#7d8da0;
  cursor:pointer;font:inherit;font-size:12.5px;font-weight:550;padding:5px 12px;
  border-radius:6px;display:flex;align-items:center;gap:6px;
  transition:color .15s,background .15s;white-space:nowrap}
.sh-hdr .seg button:hover{color:#e6edf3}
.sh-hdr .seg button.on{color:#04222e;background:linear-gradient(180deg,#38bdf8,#0ea5e9);
  box-shadow:0 1px 0 rgba(255,255,255,.25) inset,0 2px 8px rgba(14,165,233,.35)}

.sh-hdr .group{display:flex;align-items:center;gap:3px;background:rgba(255,255,255,0.04);
  border:1px solid rgba(255,255,255,0.12);border-radius:9px;padding:3px}
.sh-hdr .icon{width:16px;height:16px;display:block}
.sh-hdr .icon-btn{height:30px;min-width:30px;padding:0 7px;border-radius:6px;display:flex;
  align-items:center;justify-content:center;gap:7px;color:#e6edf3;background:transparent;
  border:1px solid transparent;cursor:pointer;font:inherit;font-size:12px;
  transition:background .15s,border-color .15s,color .15s;position:relative;white-space:nowrap}
.sh-hdr .icon-btn:hover{background:rgba(255,255,255,0.07)}
.sh-hdr .icon-btn:disabled{opacity:.4;cursor:not-allowed;background:transparent}
.sh-hdr .icon-btn.active{background:rgba(14,165,233,0.16);border-color:rgba(14,165,233,0.4);color:#38bdf8}
.sh-hdr .icon-btn .chev{width:12px;height:12px;opacity:.7}

.sh-hdr .scene-seg{display:flex;gap:2px}
.sh-hdr .scene-seg button{width:30px;height:30px;border-radius:6px;display:grid;place-items:center;
  background:transparent;border:1px solid transparent;color:#e6edf3;cursor:pointer;
  transition:background .15s,border-color .15s,color .15s}
.sh-hdr .scene-seg button:hover{background:rgba(255,255,255,0.07)}
.sh-hdr .scene-seg button.on{background:rgba(14,165,233,0.16);border-color:rgba(14,165,233,0.4);color:#38bdf8}
.sh-hdr .scene-seg .icon{width:17px;height:17px}

.sh-hdr .online{display:flex;align-items:center;gap:8px;height:30px;padding:0 10px 0 11px;
  border-radius:6px;background:transparent;border:1px solid transparent;cursor:pointer;font:inherit}
.sh-hdr .online:hover{background:rgba(255,255,255,0.05)}
.sh-hdr .online .dot{width:7px;height:7px;border-radius:50%;background:#38bdf8;
  box-shadow:0 0 0 0 rgba(56,189,248,.6);animation:sh-pulse 2.6s infinite}
.sh-hdr .online.off .dot{background:#7d8da0;animation:none}
.sh-hdr .online .lbl{font-size:12px;color:#e6edf3;white-space:nowrap}
.sh-hdr .online .lbl b{font-weight:600}
.sh-hdr .online.off .lbl{color:#7d8da0}
@keyframes sh-pulse{0%{box-shadow:0 0 0 0 rgba(56,189,248,.5)}70%{box-shadow:0 0 0 6px rgba(56,189,248,0)}100%{box-shadow:0 0 0 0 rgba(56,189,248,0)}}
.sh-hdr .switch{position:relative;width:34px;height:19px;border-radius:999px;flex:none;
  background:rgba(255,255,255,0.18);border:1px solid rgba(255,255,255,0.12);transition:background .18s}
.sh-hdr .switch::after{content:"";position:absolute;top:1.5px;left:1.5px;width:14px;height:14px;
  border-radius:50%;background:#dfe7ef;transition:transform .18s}
.sh-hdr .switch.on{background:linear-gradient(180deg,#38bdf8,#0ea5e9);border-color:transparent}
.sh-hdr .switch.on::after{transform:translateX(15px);background:#fff}

.sh-hdr .bell-btn .badge{position:absolute;top:-4px;right:-4px;min-width:16px;height:16px;padding:0 4px;
  border-radius:8px;background:#ff6b6b;color:#fff;font-size:10px;font-weight:600;
  line-height:16px;text-align:center;box-shadow:0 0 0 2px #04060a}

.sh-hdr .chip{display:flex;align-items:center;gap:9px;height:34px;padding:0 8px 0 5px;border-radius:9px;
  border:1px solid transparent;background:transparent;cursor:pointer;font:inherit;
  transition:background .15s,border-color .15s}
.sh-hdr .chip:hover{background:rgba(255,255,255,0.06);border-color:rgba(255,255,255,0.12)}
.sh-hdr .avatar{width:26px;height:26px;border-radius:50%;flex:none;display:grid;place-items:center;
  font-size:11px;font-weight:650;color:#04222e;
  background:linear-gradient(135deg,#38bdf8,#0ea5e9);box-shadow:0 1px 0 rgba(255,255,255,.3) inset}
.sh-hdr .who{display:flex;flex-direction:column;line-height:1.15;text-align:left}
.sh-hdr .who b{font-size:12.5px;font-weight:600;color:#eef3f8}
.sh-hdr .who span{font-size:9.5px;letter-spacing:.06em;text-transform:uppercase;color:#7d8da0}
.sh-hdr .chip .chev{width:13px;height:13px;color:#7d8da0}

.sh-hdr .pop{position:absolute;top:50px;z-index:120;background:#0a0f17;
  border:1px solid rgba(255,255,255,0.12);border-radius:11px;box-shadow:0 20px 50px rgba(0,0,0,.6)}
.sh-hdr .pop-head{display:flex;align-items:center;justify-content:space-between;padding:13px 15px 11px}
.sh-hdr .pop-head h3{font-size:16px;font-weight:600;color:#f3f7fb}
.sh-hdr .pop-head .sub{font-size:11px;color:#7d8da0}

.sh-hdr .pop-alerts{right:0;width:340px;max-height:70vh;overflow-y:auto}
.sh-hdr .filters{display:flex;gap:6px;padding:0 15px 12px}
.sh-hdr .filters button{flex:1;font:inherit;font-size:11px;color:#7d8da0;background:rgba(255,255,255,.05);
  border:1px solid rgba(255,255,255,0.12);border-radius:6px;padding:5px 0;cursor:pointer;transition:.12s}
.sh-hdr .filters button:hover{color:#e6edf3}
.sh-hdr .filters button.on{color:#04222e;background:#38bdf8;border-color:transparent;font-weight:600}
.sh-hdr .alerts-empty{padding:4px 15px 14px;font-size:12px;color:#7d8da0}
.sh-hdr .alert-row{padding:11px 15px;border-top:1px solid rgba(255,255,255,0.08)}
.sh-hdr .alert-row .top{display:flex;justify-content:space-between;align-items:baseline;gap:8px}
.sh-hdr .alert-row .sev{font-size:12px;font-weight:650}
.sh-hdr .alert-row .time{font-size:10.5px;color:#7d8da0;font-variant-numeric:tabular-nums}
.sh-hdr .alert-row .msg{font-size:12.5px;color:#dfe7ef;margin-top:3px}

.sh-hdr .pop-account{right:0;min-width:214px;padding:6px}
.sh-hdr .pop-account .acc-head{padding:8px 9px 10px;border-bottom:1px solid rgba(255,255,255,0.08);
  margin-bottom:5px;display:flex;align-items:center;gap:10px}
.sh-hdr .pop-account .acc-head b{font-size:13px;color:#eef3f8;display:block}
.sh-hdr .pop-account .acc-head span{font-size:9.5px;text-transform:uppercase;letter-spacing:.06em;color:#7d8da0}
.sh-hdr .pop-account a,.sh-hdr .pop-account button{display:flex;align-items:center;gap:10px;width:100%;
  text-align:left;font:inherit;font-size:12.5px;color:#e6edf3;background:transparent;border:0;cursor:pointer;
  padding:9px;border-radius:6px;transition:background .12s}
.sh-hdr .pop-account a:hover,.sh-hdr .pop-account button:hover{background:rgba(255,255,255,.07)}
.sh-hdr .pop-account .sep{height:1px;background:rgba(255,255,255,0.08);margin:5px 2px}
.sh-hdr .pop-account .danger{color:#ff8d8d}
.sh-hdr .pop-account .danger:hover{background:rgba(255,80,80,.12)}
.sh-hdr .pop-account .mi{width:15px;height:15px;color:#7d8da0;flex:none}
.sh-hdr .pop-account .danger .mi{color:#ff8d8d}
`;
