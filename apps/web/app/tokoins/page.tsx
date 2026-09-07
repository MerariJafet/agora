"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import {
  getTokoinChainExport,
  getTokoinPublicReadiness,
  getTokoinStatus,
  type TokoinChainExport,
  type TokoinPublicReadiness,
  type TokoinStatus,
} from "@/lib/tokoins";

function acerosLabel(aceros: number | null | undefined): string {
  if (aceros == null) return "pendiente";
  return `${(aceros / 100_000_000).toLocaleString(undefined, {
    maximumFractionDigits: 8,
  })} TOKOIN`;
}

function shortHash(value: string | null | undefined): string {
  if (!value) return "genesis";
  return `${value.slice(0, 12)}...${value.slice(-8)}`;
}

export default function TokoinsPage() {
  const [status, setStatus] = useState<TokoinStatus | null>(null);
  const [chain, setChain] = useState<TokoinChainExport | null>(null);
  const [publicReadiness, setPublicReadiness] = useState<TokoinPublicReadiness | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const [currentStatus, currentChain, currentPublicReadiness] = await Promise.all([
          getTokoinStatus(),
          getTokoinChainExport(250),
          getTokoinPublicReadiness().catch(() => null),
        ]);
        if (!cancelled) {
          setStatus(currentStatus);
          setChain(currentChain);
          setPublicReadiness(currentPublicReadiness);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "No se pudo cargar TOKOIN");
        }
      }
    };
    void load();
    const timer = setInterval(load, 30_000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, []);

  const visibleEntries = useMemo(
    () => [...(chain?.ledger_entries ?? [])].slice(-12).reverse(),
    [chain?.ledger_entries],
  );
  const visibleWallets = useMemo(
    () => [...(chain?.wallets ?? [])].sort((a, b) => b.balance_aceros - a.balance_aceros).slice(0, 12),
    [chain?.wallets],
  );

  return (
    <main className="plaza tokoin-page">
      <Link className="back" href="/world">← back to World</Link>
      <div className="challenge-hero">
        <div>
          <p className="eyebrow">TOKOIN Testnet Explorer</p>
          <h2>TOKOIN</h2>
          <p className="sub">
            Cadena interna verificable para recompensas de AGORA. Muestra supply,
            bloques, wallets y transacciones sin exponer secretos ni convertir
            TOKOIN en una criptomoneda publica descentralizada.
          </p>
        </div>
        <span className={`badge ${chain?.verification.valid ? "ok" : "revoked"}`}>
          {chain?.verification.valid ? "valid" : "checking"}
        </span>
      </div>

      {error && <p className="empty">{error}</p>}

      <section className="tokoin-grid">
        <article className="paper-card">
          <h3>Constitución monetaria</h3>
          <dl className="compact-facts">
            <div><dt>Supply fijo</dt><dd>{acerosLabel(status?.max_supply_aceros)}</dd></div>
            <div><dt>Treasury</dt><dd>{acerosLabel(status?.treasury_balance_aceros)}</dd></div>
            <div><dt>Circulante</dt><dd>{acerosLabel(status?.circulating_supply_aceros)}</dd></div>
            <div><dt>Wallets</dt><dd>{status?.wallet_count ?? "—"}</dd></div>
            <div><dt>Genesis hash</dt><dd>{shortHash(status?.genesis_hash)}</dd></div>
          </dl>
        </article>

        <article className="paper-card">
          <h3>Cadena</h3>
          <dl className="compact-facts">
            <div><dt>Bloques</dt><dd>{chain?.verification.blocks ?? 0}</dd></div>
            <div><dt>Entradas selladas</dt><dd>{chain?.verification.sealed_entries ?? 0}</dd></div>
            <div><dt>Pendientes</dt><dd>{chain?.verification.pending_entries ?? 0}</dd></div>
            <div><dt>Transferencias firmadas</dt><dd>{chain?.verification.signed_transfer_entries ?? 0}</dd></div>
            <div><dt>Tip hash</dt><dd>{shortHash(chain?.verification.tip_hash)}</dd></div>
          </dl>
          <p className="subtle-note">
            Verificación externa: <code>scripts/verify-tokoin-chain.py http://127.0.0.1:8700/v1/tokoins/blockchain/export</code>
          </p>
        </article>

        <article className="paper-card">
          <h3>Candidato público EVM</h3>
          <dl className="compact-facts">
            <div><dt>Etapa</dt><dd>{publicReadiness?.stage ?? "verificando"}</dd></div>
            <div><dt>Bundle reproducible</dt><dd>{publicReadiness?.candidate_bundle.integrity_valid ? "válido" : "no verificado"}</dd></div>
            <div><dt>Auditoría externa</dt><dd>{publicReadiness?.independent_audit.complete ? "aceptada" : "pendiente"}</dd></div>
            <div><dt>Base Sepolia</dt><dd>{publicReadiness?.base_sepolia_deployed ? "desplegado" : "no desplegado"}</dd></div>
            <div><dt>Mainnet / mercado</dt><dd>{publicReadiness?.market_ready ? "habilitado" : "no autorizado"}</dd></div>
          </dl>
          <p className="subtle-note">
            El ledger interno y el candidato ERC-20 son sistemas distintos. Un bundle válido
            permite auditar el mismo bytecode; no prueba despliegue, descentralización ni valor.
          </p>
          {publicReadiness?.candidate_bundle.bundle_sha256 && (
            <code>{shortHash(publicReadiness.candidate_bundle.bundle_sha256)}</code>
          )}
        </article>
      </section>

      <section className="challenge-paper-grid">
        <article className="challenge-paper-main">
          <h3>Bloques</h3>
          <div className="paper-timeline">
            {(chain?.blocks ?? []).map((block) => (
              <article key={block.block_id} className="paper-post">
                <div className="paper-post-meta">
                  <span>height {block.height}</span>
                  <time>{new Date(block.created_at).toLocaleString()}</time>
                  <code>{block.block_id}</code>
                </div>
                <dl className="compact-facts">
                  <div><dt>Rango</dt><dd>{block.first_sequence} - {block.last_sequence}</dd></div>
                  <div><dt>Merkle</dt><dd>{shortHash(block.transaction_merkle_root)}</dd></div>
                  <div><dt>Previo</dt><dd>{shortHash(block.previous_block_hash)}</dd></div>
                  <div><dt>Hash</dt><dd>{shortHash(block.block_hash)}</dd></div>
                </dl>
              </article>
            ))}
            {!chain?.blocks?.length && <p className="empty">Aun no hay bloques sellados.</p>}
          </div>
        </article>

        <aside className="challenge-paper-side">
          <section className="paper-card">
            <h3>Top wallets</h3>
            <ul className="compact-list">
              {visibleWallets.map((wallet) => (
                <li key={wallet.wallet_id}>
                  <strong>{wallet.label}</strong><br />
                  <code>{wallet.wallet_address}</code><br />
                  {acerosLabel(wallet.balance_aceros)}
                </li>
              ))}
            </ul>
          </section>

          <section className="paper-card">
            <h3>Últimas transacciones</h3>
            <ul className="compact-list">
              {visibleEntries.map((entry) => (
                <li key={entry.entry_id}>
                  <strong>#{entry.sequence} {entry.entry_type}</strong><br />
                  {acerosLabel(entry.amount)} · {entry.reason}<br />
                  <code>{shortHash(entry.entry_hash)}</code>
                  {entry.authorization && (
                    <>
                      <br />
                      <span>{entry.authorization.authorization_type}</span>
                    </>
                  )}
                </li>
              ))}
            </ul>
          </section>
        </aside>
      </section>
    </main>
  );
}
