"use client";

// useFlipReorder — reorden animado sin librerías (técnica FLIP + Web
// Animations API). Los hijos del contenedor marcados con data-flip-key se
// deslizan suavemente a su nueva posición cuando el orden cambia (p.ej. al
// refrescar el digest). Respeta prefers-reduced-motion: sin animación.

import { useLayoutEffect, useRef } from "react";

export function useFlipReorder<T extends HTMLElement>(orderSignature: string) {
  const containerRef = useRef<T | null>(null);
  const previousRects = useRef(new Map<string, DOMRect>());

  useLayoutEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const items = Array.from(
      container.querySelectorAll<HTMLElement>("[data-flip-key]"),
    );
    const nextRects = new Map<string, DOMRect>();
    for (const item of items) {
      nextRects.set(item.dataset.flipKey!, item.getBoundingClientRect());
    }
    const reducedMotion =
      globalThis.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
    if (!reducedMotion && typeof Element.prototype.animate === "function") {
      for (const item of items) {
        const key = item.dataset.flipKey!;
        const prev = previousRects.current.get(key);
        const next = nextRects.get(key);
        if (!prev || !next) continue;
        const dx = prev.left - next.left;
        const dy = prev.top - next.top;
        if (Math.abs(dx) < 1 && Math.abs(dy) < 1) continue;
        item.animate(
          [
            { transform: `translate(${dx}px, ${dy}px)` },
            { transform: "translate(0, 0)" },
          ],
          { duration: 280, easing: "cubic-bezier(0.22, 1, 0.36, 1)" },
        );
      }
    }
    previousRects.current = nextRects;
  }, [orderSignature]);

  return containerRef;
}
