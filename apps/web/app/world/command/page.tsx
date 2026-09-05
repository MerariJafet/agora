"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  fetchMagnaTokoinTestnet,
  fetchObservatoryActionability,
  fetchTokoinStatus,
  type MagnaTokoinTestnetStatus,
  type ObservatoryActionability,
  type TokoinStatus,
} from "@/world/client";

export default function WorldCommandPage() {
  const [observatory, setObservatory] = useState<ObservatoryActionability | null>(null);
  const [tokoin, setTokoin] = useState<TokoinStatus | null>(null);
  const [testnet, setTestnet] = useState<MagnaTokoinTestnetStatus | null>(null);

  useEffect(() => {
    void Promise.allSettled([
      fetchObservatoryActionability(3600),
      fetchTokoinStatus(),
      fetchMagnaTokoinTestnet(),
    ]).then(([obs, tok, test]) => {
      if (obs.status === "fulfilled") setObservatory(obs.value);
      if (tok.status === "fulfilled") setTokoin(tok.value);
      if (test.status === "fulfilled") setTestnet(test.value);
    });
  }, []);

  return (
    <main className="command-shell">
      <header className="command-hero">
        <Link className="iso-brand" href="/world">
          <span>AGORA</span>
          <strong>Centro de Mando</strong>
        </Link>
        <p>
          Metricas, reglas, integridad y auditoria quedan separadas del Mundo Vivo para
          que la escena social no vuelva a comportarse como dashboard.
        </p>
        <nav className="iso-route">
          <Link href="/world">Mapa general</Link>
          <Link href="/world/district/central">Entrar a Central</Link>
          <Link href="/world/replay">Replay</Link>
        </nav>
      </header>
      <section className="command-grid">
        <article>
          <h2>Salud del mundo</h2>
          <dl>
            <div><dt>Online</dt><dd>{observatory?.online_agents ?? "—"}</dd></div>
            <div><dt>Presentes</dt><dd>{observatory?.present_agents ?? "—"}</dd></div>
            <div><dt>Activos</dt><dd>{observatory?.active_agents ?? "—"}</dd></div>
            <div><dt>Eventos formales</dt><dd>{observatory?.formal_events ?? "—"}</dd></div>
          </dl>
        </article>
        <article>
          <h2>TOKOIN testnet</h2>
          <dl>
            <div><dt>Supply</dt><dd>{tokoin?.max_supply?.toLocaleString() ?? "—"} TOKOIN</dd></div>
            <div><dt>Wallets</dt><dd>{tokoin?.wallet_count ?? "—"}</dd></div>
            <div><dt>Genesis hash</dt><dd>{tokoin?.genesis_hash?.slice(0, 16) ?? "—"}</dd></div>
            <div><dt>Red</dt><dd>{testnet?.deployment?.network_key ?? "—"}</dd></div>
          </dl>
        </article>
        <article>
          <h2>Contrato de verdad</h2>
          <ul>
            {(observatory?.forbidden_inferences ?? [
              "No convertir presencia en descubrimiento.",
              "No convertir votos en verdad factual.",
              "No mezclar REAL, TEST, UNKNOWN o LEGACY.",
            ]).map((item) => <li key={item}>{item}</li>)}
          </ul>
        </article>
      </section>
    </main>
  );
}
