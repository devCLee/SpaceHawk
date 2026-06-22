'use client'

import dynamic from 'next/dynamic'
import React from 'react';
import type { CesiumType } from '../types/cesium';
import type { Position } from '../types/position';
import type { TleObject } from '../utils/sgp4FromTle';
import type { Debris } from '@/lib/orbital-engine';

const CesiumDynamicComponent = dynamic(() => import('./CesiumComponent'), {
    ssr: false
});

export const CesiumWrapper: React.FunctionComponent<{
  positions: Position[];
  tleEntries?: TleObject[];
  debrisEntries?: Debris[];
}> = ({ positions, tleEntries, debrisEntries }) => {
  const [CesiumJs, setCesiumJs] = React.useState<CesiumType | null>(null);

  React.useEffect(() => {
    if (CesiumJs !== null) return;
    const CesiumImportPromise = import("cesium");
    Promise.all([CesiumImportPromise]).then((promiseResults) => {
      const { ...Cesium } = promiseResults[0];
      setCesiumJs(Cesium);
    });
  }, [CesiumJs]);

  return CesiumJs ? (
    <CesiumDynamicComponent
      CesiumJs={CesiumJs}
      positions={positions}
      tleEntries={tleEntries}
      debrisEntries={debrisEntries}
    />
  ) : null;
};

export default CesiumWrapper;