/** Lightweight toast store (no external deps). */

import { create } from "zustand";

export type ToastVariant = "default" | "success" | "destructive";

export interface Toast {
  id: number;
  title: string;
  description?: string;
  variant: ToastVariant;
}

interface ToastState {
  toasts: Toast[];
  push: (toast: Omit<Toast, "id">) => void;
  dismiss: (id: number) => void;
}

let toastId = 0;
const MAX_TOASTS = 4;
const AUTO_DISMISS_MS = 4000;

export const useToastStore = create<ToastState>((set) => ({
  toasts: [],

  push: (toast) => {
    toastId += 1;
    const id = toastId;
    set((state) => ({
      toasts: [...state.toasts.slice(-(MAX_TOASTS - 1)), { ...toast, id }],
    }));
    // Auto dismiss
    if (typeof window !== "undefined") {
      window.setTimeout(() => {
        set((state) => ({ toasts: state.toasts.filter((t) => t.id !== id) }));
      }, AUTO_DISMISS_MS);
    }
  },

  dismiss: (id) =>
    set((state) => ({ toasts: state.toasts.filter((t) => t.id !== id) })),
}));

/** Imperative helpers. */
export const toast = {
  success: (title: string, description?: string) =>
    useToastStore.getState().push({ title, description, variant: "success" }),
  error: (title: string, description?: string) =>
    useToastStore.getState().push({ title, description, variant: "destructive" }),
  info: (title: string, description?: string) =>
    useToastStore.getState().push({ title, description, variant: "default" }),
};
