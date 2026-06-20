/**
 * toaster.tsx — Sonner toast with RawBlock theme
 * =================================================
 * Mounted once in App.tsx. All toasts go through sonner's
 * toast() function which components import directly.
 */

import { Toaster as SonnerToaster } from 'sonner';

export function Toaster() {
  return (
    <SonnerToaster
      position="bottom-right"
      toastOptions={{
        unstyled: true,
        classNames: {
          toast:
            'flex items-center gap-2 border-thick border-border bg-card text-foreground font-mono text-small px-sp-3 py-sp-2 w-[360px]',
          title: 'font-bold uppercase tracking-chip text-tiny',
          description: 'text-muted-foreground text-tiny',
          success: 'border-success text-success',
          error: 'border-error text-error',
          warning: 'border-warning text-warning',
          info: 'border-info text-info',
        },
      }}
    />
  );
}
