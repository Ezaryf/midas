"use client";

import { useEffect, useRef } from "react";

export function useRenderDebug(name: string) {
  const renderCountRef = useRef(0);

  renderCountRef.current += 1;

  useEffect(() => {
    if (process.env.NODE_ENV !== "development") return;
    console.debug(`[render] ${name} #${renderCountRef.current}`);
  });
}
