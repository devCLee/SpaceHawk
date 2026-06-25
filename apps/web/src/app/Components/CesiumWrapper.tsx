'use client'

import dynamic from 'next/dynamic'
import React from 'react';
import type { CesiumType } from '../types/cesium';
import type { Position } from '../types/position';
import type { TleObject } from '../utils/sgp4FromTle';
import type { Debris } from '@/lib/orbital-engine';

// Cesium is loaded at runtime as a prebuilt UMD via a plain <script> tag (exactly
// how Cesium's own CDN demos load it) and handed to CesiumComponent as a prop.
// It is deliberately NOT imported/bundled by webpack: bundling the cesium chunk
// in the Next 16 prod build crashed the renderer while *evaluating* the chunk
// (confirmed independent of minify, data, and extensions). A native <script>
// eval of the same prebuilt UMD is fine.
const CESIUM_SCRIPT_SRC = '/cesium/Cesium.js';

// CesiumComponent itself never imports cesium, so its dynamic chunk is small.
const CesiumDynamicComponent = dynamic(() => import('./CesiumComponent'), {
  ssr: false,
});

const fullScreenBox: React.CSSProperties = {
  height: 'calc(100vh - 56px)',
  width: '100vw',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  background: '#0b0f1a',
  fontFamily: 'system-ui, sans-serif',
  fontSize: 13,
};

/** Load the prebuilt Cesium UMD once and resolve with the `window.Cesium`
 *  namespace. CESIUM_BASE_URL must be set before Cesium resolves its worker /
 *  asset URLs, so we set it up front. Reuses an in-flight/loaded script tag. */
function loadCesium(): Promise<CesiumType> {
  return new Promise((resolve, reject) => {
    if (typeof window === 'undefined') {
      reject(new Error('cesium can only load in the browser'));
      return;
    }
    if (window.Cesium) {
      resolve(window.Cesium);
      return;
    }
    (window as unknown as { CESIUM_BASE_URL?: string }).CESIUM_BASE_URL = '/cesium';
    // Cesium widget CSS (timeline / animation controls). Loaded from the copied
    // runtime assets rather than bundled, matching the externalised library.
    if (!document.querySelector('link[data-cesium-widgets]')) {
      const link = document.createElement('link');
      link.rel = 'stylesheet';
      link.href = '/cesium/Widgets/widgets.css';
      link.setAttribute('data-cesium-widgets', '');
      document.head.appendChild(link);
    }
    const settle = () =>
      window.Cesium
        ? resolve(window.Cesium)
        : reject(new Error('Cesium global missing after script load'));
    const fail = () => reject(new Error('failed to load ' + CESIUM_SCRIPT_SRC));
    const existing = document.querySelector<HTMLScriptElement>(
      `script[src="${CESIUM_SCRIPT_SRC}"]`
    );
    if (existing) {
      existing.addEventListener('load', settle);
      existing.addEventListener('error', fail);
      return;
    }
    const script = document.createElement('script');
    script.src = CESIUM_SCRIPT_SRC;
    script.async = true;
    script.onload = settle;
    script.onerror = fail;
    document.head.appendChild(script);
  });
}

export const CesiumWrapper: React.FunctionComponent<{
  positions: Position[];
  tleEntries?: TleObject[];
  debrisEntries?: Debris[];
}> = ({ positions, tleEntries, debrisEntries }) => {
  const [CesiumJs, setCesiumJs] = React.useState<CesiumType | null>(null);
  const [loadError, setLoadError] = React.useState<string | null>(null);

  React.useEffect(() => {
    let cancelled = false;
    loadCesium()
      .then((cesium) => {
        if (!cancelled) setCesiumJs(cesium);
      })
      .catch((err) => {
        if (!cancelled) setLoadError(String(err?.message ?? err));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (loadError) {
    return (
      <div role="alert" style={{ ...fullScreenBox, color: '#e5e7eb', textAlign: 'center', padding: 24 }}>
        {`지구본을 불러오지 못했습니다.\n${loadError}`}
      </div>
    );
  }

  if (!CesiumJs) {
    return <div style={{ ...fullScreenBox, color: '#6b7280' }}>지구본 로딩 중…</div>;
  }

  return (
    <CesiumDynamicComponent
      CesiumJs={CesiumJs}
      positions={positions}
      tleEntries={tleEntries}
      debrisEntries={debrisEntries}
    />
  );
};

export default CesiumWrapper;
