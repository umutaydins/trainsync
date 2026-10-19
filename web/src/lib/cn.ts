import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

/** Class names merged the Tailwind way: a later `px-4` replaces an earlier `px-2`. */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
