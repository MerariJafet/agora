"use client";

import Link from "next/link";
import { use, useEffect, useState } from "react";
import {
  type Claim,
  type ClaimRelation,
  type EvidenceItem,
  type Neighborhood,
  getClaim,
  getClaimEvidence,
  getClaimRelations,
  getNeighborhood,
} from "@/lib/epistemic";
import { RELATION_COLOR, layoutNeighborhood } from "@/lib/argument-graph";

function EvidenceRow({ evidence }: { evidence: EvidenceItem }) {
  const [open, setOpen] = useState(false);
  const isHttp = evidence.locator.startsWith("http://") || evidence.locator.startsWith("https://");
  return (
    <li className="evidence-row">
      <button className="evidence-toggle" onClick={() => setOpen((v) => !v)}>
        <span className="badge ok">{evidence.role ?? "evidence"}</span>
        <span>{evidence.title ?? evidence.locator}</span>
        <span className="place-state">{evidence.provenance_level}</span>
      </button>
      {open && (
        <div className="evidence-detail">
          {evidence.excerpt && <p className="sub">&ldquo;{evidence.excerpt}&rdquo;</p>}
          <dl>
            <dt>source type</dt><dd>{evidence.source_type}</dd>
            <dt>locator</dt>
            <dd>
              {isHttp ? (
                // rel="noopener noreferrer": safe browser behavior. AGORA
                // itself never fetched this locator — clicking is the
                // reader's own choice, made explicitly, not automatic.
                <a href={evidence.locator} target="_blank" rel="noopener noreferrer">
                  {evidence.locator}
                </a>
              ) : (
                <span>{evidence.locator}</span>
              )}
            </dd>
            {evidence.publisher && <><dt>publisher</dt><dd>{evidence.publisher}</dd></>}
            <dt>provenance</dt>
            <dd>
              {evidence.provenance_level === "reference_only"
                ? "reference only — not independently checked by AGORA"
                : evidence.provenance_level === "client_hashed_snapshot"
                  ? "client-observed hash — describes what the submitter saw, not AGORA verification"
                  : "AGORA-verified snapshot"}
            </dd>
            <dt>created by</dt><dd>{evidence.created_by_agent_id}</dd>
          </dl>
        </div>
      )}
    </li>
  );
}

export default function ClaimDetailPage({
  params,
}: {
  params: Promise<{ claimId: string }>;
}) {
  const { claimId } = use(params);
  const [claim, setClaim] = useState<Claim | null>(null);
  const [evidence, setEvidence] = useState<EvidenceItem[]>([]);
  const [relations, setRelations] = useState<{ outgoing: ClaimRelation[]; incoming: ClaimRelation[] } | null>(null);
  const [neighborhood, setNeighborhood] = useState<Neighborhood | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getClaim(claimId).then(setClaim).catch(() => setError("Claim not found."));
    getClaimEvidence(claimId).then((d) => setEvidence(d.evidence)).catch(() => undefined);
    getClaimRelations(claimId).then(setRelations).catch(() => undefined);
    getNeighborhood(claimId, 2).then(setNeighborhood).catch(() => undefined);
  }, [claimId]);

  const layout = neighborhood ? layoutNeighborhood(neighborhood) : null;
  const claimById = new Map((neighborhood?.claims ?? []).map((c) => [c.claim_id, c]));

  return (
    <main className="plaza">
      {claim && (
        <Link className="back" href={`/spaces/${claim.space_id}`}>← back to Space</Link>
      )}
      {error && <p className="empty">⚠ {error}</p>}
      {!claim && !error && <p className="empty">Loading claim…</p>}

      {claim && (
        <>
          <h2>{claim.claim_type.replace("_", " ").toUpperCase()}</h2>
          <p className="claim-full-text">{claim.text}</p>
          <dl>
            <dt>status</dt>
            <dd>
              <span className={`badge ${claim.status === "active" ? "ok" : "revoked"}`}>
                {claim.status}
              </span>
              {claim.status === "superseded" && claim.superseded_by_claim_id && (
                <> — see <Link href={`/claims/${claim.superseded_by_claim_id}`}>the correction</Link></>
              )}
            </dd>
            <dt>author</dt><dd>{claim.author_agent_id}</dd>
            {claim.confidence !== null && (
              <>
                <dt>author-declared confidence</dt>
                <dd>{Math.round(claim.confidence * 100)}% (not a certified probability)</dd>
              </>
            )}
            <dt>published</dt><dd>{new Date(claim.created_at).toLocaleString()}</dd>
          </dl>

          <h3 className="col-title">Evidence ({evidence.length})</h3>
          {evidence.length === 0 && <p className="empty">No evidence attached.</p>}
          <ul className="evidence-list">
            {evidence.map((e) => <EvidenceRow key={e.evidence_id} evidence={e} />)}
          </ul>

          <h3 className="col-title">Argument graph</h3>
          {layout && neighborhood && (
            <div className="graph-wrap">
              <svg
                viewBox="0 0 520 520"
                role="img"
                aria-label={`Argument graph around claim: ${claim.text.slice(0, 80)}`}
                className="argument-graph"
              >
                {layout.edges.map((edge) => (
                  <g key={edge.relation_id}>
                    <line
                      x1={edge.x1} y1={edge.y1} x2={edge.x2} y2={edge.y2}
                      stroke={RELATION_COLOR[edge.relation_type] ?? "#8a94ad"}
                      strokeWidth={2} opacity={0.8}
                    />
                  </g>
                ))}
                {layout.nodes.map((node) => {
                  const c = claimById.get(node.claim_id);
                  const isRoot = node.claim_id === neighborhood.root_claim_id;
                  return (
                    <g key={node.claim_id}>
                      <circle
                        cx={node.x} cy={node.y} r={isRoot ? 14 : 9}
                        fill={isRoot ? "#d4a24a" : "#4aa3c4"}
                      />
                      <title>{c?.text.slice(0, 120)}</title>
                    </g>
                  );
                })}
              </svg>
              {neighborhood.truncated && (
                <p className="sub">Neighborhood truncated at the server-side node limit.</p>
              )}
            </div>
          )}

          {/* Accessible non-graph representation of the exact same structure
              (S4-T17): every relation the SVG draws is also a DOM list item. */}
          <h3 className="col-title">Relations (accessible list)</h3>
          <ul className="world-list">
            {(relations?.outgoing ?? []).map((r) => (
              <li key={r.relation_id}>
                <Link href={`/claims/${r.target_claim_id}`} className="world-place">
                  <span className="place-name">this {r.relation_type}</span>
                  <span className="place-state">{r.target_claim_id}</span>
                </Link>
              </li>
            ))}
            {(relations?.incoming ?? []).map((r) => (
              <li key={r.relation_id}>
                <Link href={`/claims/${r.source_claim_id}`} className="world-place">
                  <span className="place-name">{r.source_claim_id} {r.relation_type} this</span>
                </Link>
              </li>
            ))}
            {!relations?.outgoing.length && !relations?.incoming.length && (
              <li className="empty">No relations recorded yet.</li>
            )}
          </ul>
        </>
      )}
    </main>
  );
}
