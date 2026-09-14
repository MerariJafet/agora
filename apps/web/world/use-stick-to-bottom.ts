"use client";

// useStickToBottom — autoscroll de chat con pausa inteligente. Extraído del
// patrón de district-chat para compartirlo con el chat global de /world: la
// lista se mantiene pegada al fondo mientras el usuario está abajo; si sube a
// leer, se deja de forzar el scroll hasta que vuelva a acercarse al fondo.

import { useEffect, useRef, type UIEvent } from "react";

const AUTOSCROLL_THRESHOLD_PX = 48;

export function useStickToBottom<T extends HTMLElement>(dependency: unknown) {
  const listRef = useRef<T | null>(null);
  const stickToBottomRef = useRef(true);

  useEffect(() => {
    const list = listRef.current;
    if (!list || !stickToBottomRef.current) return;
    list.scrollTop = list.scrollHeight;
  }, [dependency]);

  const onScroll = (event: UIEvent<T>) => {
    const list = event.currentTarget;
    stickToBottomRef.current =
      list.scrollHeight - list.scrollTop - list.clientHeight < AUTOSCROLL_THRESHOLD_PX;
  };

  return { listRef, onScroll };
}
