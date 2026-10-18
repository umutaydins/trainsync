/**
 * Rest-over signals: vibration, a short beep and (only if already granted) a notification. Each
 * one is feature-detected and never throws: a missing API or a denied permission just means that
 * signal is skipped. Permission is only ever asked from a user gesture (`requestNotifications`).
 */

type AudioContextCtor = typeof AudioContext;

let audio: AudioContext | null = null;

function audioContextCtor(): AudioContextCtor | null {
  if (typeof window === "undefined") return null;
  const w = window as unknown as { AudioContext?: AudioContextCtor; webkitAudioContext?: AudioContextCtor };
  return w.AudioContext ?? w.webkitAudioContext ?? null;
}

/** Call from a tap: browsers only let audio start after a user gesture. */
export function primeAudio(): void {
  try {
    const Ctor = audioContextCtor();
    if (!Ctor) return;
    audio ??= new Ctor();
    if (audio.state === "suspended") void audio.resume().catch(() => undefined);
  } catch {
    audio = null;
  }
}

export function beep(durationMs = 180, frequency = 880): void {
  try {
    if (!audio) primeAudio();
    if (!audio) return;
    const oscillator = audio.createOscillator();
    const gain = audio.createGain();
    oscillator.type = "sine";
    oscillator.frequency.value = frequency;
    gain.gain.setValueAtTime(0.2, audio.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, audio.currentTime + durationMs / 1000);
    oscillator.connect(gain).connect(audio.destination);
    oscillator.start();
    oscillator.stop(audio.currentTime + durationMs / 1000);
  } catch {
    // no audio
  }
}

export function vibrate(pattern: number | number[] = [200, 100, 200]): void {
  try {
    if (typeof navigator !== "undefined" && typeof navigator.vibrate === "function") navigator.vibrate(pattern);
  } catch {
    // no vibration
  }
}

export function notificationsSupported(): boolean {
  return typeof window !== "undefined" && "Notification" in window;
}

export function notificationPermission(): NotificationPermission | "unsupported" {
  return notificationsSupported() ? Notification.permission : "unsupported";
}

/** Ask for permission; call only from a click handler. */
export async function requestNotifications(): Promise<NotificationPermission | "unsupported"> {
  if (!notificationsSupported()) return "unsupported";
  try {
    return await Notification.requestPermission();
  } catch {
    return Notification.permission;
  }
}

export function notify(title: string, body: string): void {
  try {
    if (notificationPermission() !== "granted") return;
    new Notification(title, { body, tag: "trainsync-rest", silent: true });
  } catch {
    // Some mobile browsers only allow notifications from a service worker; skip.
  }
}

/** Everything at once, for the rest timer reaching zero. */
export function restOver(label: string): void {
  vibrate();
  beep();
  notify("Rest over", label ? `Next: ${label}` : "Time for the next set");
}
