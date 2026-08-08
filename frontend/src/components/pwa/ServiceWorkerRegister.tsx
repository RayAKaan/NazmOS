"use client";

import { useEffect } from "react";

export function ServiceWorkerRegister() {
  useEffect(() => {
    if (typeof window === "undefined" || !("serviceWorker" in navigator)) return;

    navigator.serviceWorker
      .register("/sw.js")
      .then((registration) => {
        console.log("NazmOS SW registered:", registration.scope);
      })
      .catch((error) => {
        console.error("NazmOS SW registration failed:", error);
      });
  }, []);

  return null;
}
