let deferredPrompt: Event | null = null;

if (typeof window !== "undefined") {
  window.addEventListener("beforeinstallprompt", (event: Event) => {
    deferredPrompt = event;
  });
}

export function isPWAInstalled(): boolean {
  return window.matchMedia("(display-mode: standalone)").matches;
}

export function canInstallPWA(): boolean {
  return deferredPrompt !== null;
}

export async function registerServiceWorker(): Promise<void> {
  if ("serviceWorker" in navigator) {
    await navigator.serviceWorker.register("/sw.js");
  }
}
