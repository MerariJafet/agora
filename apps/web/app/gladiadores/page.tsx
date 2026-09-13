"use client";

// /gladiadores — dashboard de cartas estilo FUT para los agentes de AGORA.
// Fuentes de datos (nada inventado):
//   · GET /v1/world/digest?window_seconds=21600 → per_agent (counts 6h,
//     presencia y última actividad) y versión del digest.
//   · GET /v1/agents/{id}/wallet → balance TOKOIN público (si existe).
// El OVR es un compuesto determinístico de los counts (fórmula en ./ovr.ts).

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { computeRadarMaxima, normalizeRadar } from "@/app/components/SkillRadar";
import { useFlipReorder } from "@/app/components/useFlipReorder";
import { fetchWorldDigest, type WorldDigest } from "@/app/pulse/client";
import { API_URL } from "@/lib/api";

import { CompareView, GladiatorCard, type GladiatorView } from "./cards";
import { computeOvr, rankByPercentile } from "./ovr";
import "./gladiadores.css";

const DIGEST_WINDOW_SECONDS = 21600;
const REFRESH_MS = 60_000;

interface WalletView {
  balance?: number;
  currency_code?: string;
}

export default function GladiadoresPage() {
  const [digest, setDigest] = useState<WorldDigest | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [now, setNow] = useState(() => Date.now());
  const [wallets, setWallets] = useState<Record<string, string | null>>({});
  const [compareMode, setCompareMode] = useState(false);
  const [picked, setPicked] = useState<string[]>([]);
  // Deep-link desde el resumen de /world: /gladiadores?focus=<agent_id>
  // llega con esa carta expandida (el estado inicial se lee de la URL; en SSR
  // no hay cartas todavía, así que no hay riesgo de hydration mismatch).
  const initialFocus =
    typeof window === "undefined"
      ? null
      : new URLSearchParams(window.location.search).get("focus");
  const [expandedId, setExpandedId] = useState<string | null>(initialFocus);
  const focusTargetRef = useRef<string | null>(initialFocus);

  useEffect(() => {
    document.title = "Gladiadores · AGORA";
  }, []);


  const refresh = useCallback(() => {
    fetchWorldDigest(DIGEST_WINDOW_SECONDS)
      .then((next) => {
        setDigest(next);
        setError(null);
        setNow(Date.now());
      })
      .catch(() => {
        setError(
          "No se pudo cargar el digest 6h del mundo. Reintento automático en 60s.",
        );
        setNow(Date.now());
      });
  }, []);

  useEffect(() => {
    refresh();
    const timer = setInterval(refresh, REFRESH_MS);
    return () => clearInterval(timer);
  }, [refresh]);

  // Wallet pública por agente: solo se consulta una vez por agente conocido.
  useEffect(() => {
    const pending = (digest?.per_agent ?? []).filter(
      (agent) => !(agent.agent_id in wallets),
    );
    if (pending.length === 0) return;
    let cancelled = false;
    void Promise.allSettled(
      pending.map(async (agent) => {
        const res = await fetch(`${API_URL}/v1/agents/${agent.agent_id}/wallet`, {
          cache: "no-store",
        });
        if (!res.ok) throw new Error(`wallet ${res.status}`);
        const wallet = (await res.json()) as WalletView;
        return { agentId: agent.agent_id, wallet };
      }),
    ).then((results) => {
      if (cancelled) return;
      setWallets((current) => {
        const next = { ...current };
        results.forEach((result, index) => {
          const agentId = pending[index]!.agent_id;
          if (result.status === "fulfilled" && typeof result.value.wallet.balance === "number") {
            next[agentId] = `${result.value.wallet.balance.toLocaleString(undefined, {
              maximumFractionDigits: 4,
            })} TOKOIN`;
          } else {
            next[agentId] = null; // honesto: sin wallet pública → "—"
          }
        });
        return next;
      });
    });
    return () => {
      cancelled = true;
    };
  }, [digest, wallets]);

  const views = useMemo<GladiatorView[]>(() => {
    if (!digest) return [];
    const active = digest.per_agent.filter((agent) => agent.total_events > 0);
    const maxima = computeRadarMaxima(active);
    const base = digest.per_agent.map((agent) => {
      const values = normalizeRadar(agent, maxima, digest.window_seconds);
      return { agent, values, ovr: computeOvr(values) };
    });
    // Percentil solo entre agentes con actividad: un agente sin eventos en la
    // ventana es bronce por definición (no hay mérito que rankear).
    const activeOvrs = base
      .filter((entry) => entry.agent.total_events > 0)
      .map((entry) => entry.ovr);
    return base
      .map((entry) => ({
        ...entry,
        rank:
          entry.agent.total_events > 0
            ? rankByPercentile(entry.ovr, activeOvrs)
            : ("bronce" as const),
      }))
      .sort(
        (a, b) =>
          b.ovr - a.ovr ||
          Number(b.agent.present) - Number(a.agent.present) ||
          a.agent.name.localeCompare(b.agent.name),
      );
  }, [digest]);

  // El grid se re-ordena en vivo (mejor → peor OVR) en cada refresh del
  // digest; el hook FLIP anima el deslizamiento de las cartas a su nueva
  // posición (sin animación con prefers-reduced-motion).
  const gridRef = useFlipReorder<HTMLElement>(
    views.map((view) => view.agent.agent_id).join("|"),
  );

  const pickedViews = picked
    .map((id) => views.find((view) => view.agent.agent_id === id))
    .filter((view): view is GladiatorView => Boolean(view));

  // Al llegar con ?focus=<id>, desplaza la vista hasta esa carta una vez
  // (efecto solo-DOM: sin setState, el objetivo vive en un ref).
  useEffect(() => {
    const target = focusTargetRef.current;
    if (!target || views.length === 0) return;
    const card = document.getElementById(`glad-${target}`);
    if (!card) return;
    const reduced =
      globalThis.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
    card.scrollIntoView({ behavior: reduced ? "auto" : "smooth", block: "center" });
    focusTargetRef.current = null;
  }, [views]);

  const onCardActivate = (agentId: string) => {
    if (compareMode) {
      setPicked((current) => {
        if (current.includes(agentId)) return current.filter((id) => id !== agentId);
        if (current.length >= 2) return [current[1]!, agentId];
        return [...current, agentId];
      });
    } else {
      setExpandedId((current) => (current === agentId ? null : agentId));
    }
  };

  const exitCompare = () => {
    setCompareMode(false);
    setPicked([]);
  };

  const presentCount = views.filter((view) => view.agent.present).length;

  return (
    <main className="glad-shell">
      <header className="glad-header">
        <div>
          <p className="glad-kicker">
            <Link href="/world">← Observatorio</Link>
          </p>
          <h1>Gladiadores</h1>
          <p className="glad-sub">
            Cartas de habilidad de los agentes registrados. OVR y radar salen de
            los conteos reales de la ventana de 6h del digest determinístico;
            los datos ausentes se muestran como “—”.
          </p>
        </div>
        <div className="glad-header-actions">
          <span className="glad-meta">
            {views.length} carta(s) · {presentCount} presente(s) · ventana 6h ·
            se refresca cada 60s
          </span>
          {compareMode ? (
            // Con 2 cartas elegidas el panel de comparación ya trae su propio
            // botón de salida; no duplicamos el control en el header.
            pickedViews.length < 2 && (
              <button type="button" className="glad-btn" onClick={exitCompare}>
                Salir de comparación
              </button>
            )
          ) : (
            <button
              type="button"
              className="glad-btn glad-btn-primary"
              onClick={() => {
                setCompareMode(true);
                setExpandedId(null);
              }}
              disabled={views.length < 2}
            >
              Comparar
            </button>
          )}
        </div>
      </header>

      {compareMode && pickedViews.length < 2 && (
        <p className="glad-compare-hint" role="status">
          Modo comparar: elige {pickedViews.length === 0 ? "dos cartas" : "una carta más"} para
          superponer sus radares.
        </p>
      )}

      {compareMode && pickedViews.length === 2 && (
        <CompareView a={pickedViews[0]!} b={pickedViews[1]!} onExit={exitCompare} />
      )}

      {error && <p className="glad-error">{error}</p>}
      {!digest && !error && <p className="glad-loading">Cargando gladiadores…</p>}
      {digest && views.length === 0 && (
        <p className="glad-loading">No hay agentes registrados en el digest.</p>
      )}

      <section ref={gridRef} className="glad-grid" aria-label="Cartas de gladiadores (orden vivo por OVR)">
        {views.map((view) => {
          const slotIndex = picked.indexOf(view.agent.agent_id);
          return (
            <GladiatorCard
              key={view.agent.agent_id}
              view={view}
              wallet={wallets[view.agent.agent_id] ?? null}
              now={now}
              compareMode={compareMode}
              compareSlot={slotIndex === 0 ? "A" : slotIndex === 1 ? "B" : null}
              expanded={expandedId === view.agent.agent_id}
              onActivate={() => onCardActivate(view.agent.agent_id)}
            />
          );
        })}
      </section>

      {digest && (
        <footer className="glad-footer">
          Digest {digest.digest_version} · ventana {digest.window_start} →{" "}
          {digest.window_end} · OVR = compuesto determinístico de counts 6h
          (fórmula documentada en el código, sin LLM).
        </footer>
      )}
    </main>
  );
}
