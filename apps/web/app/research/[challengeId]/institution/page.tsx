"use client";

import Link from "next/link";
import { use, useEffect, useMemo, useState } from "react";

import { whoAmI, type OwnerSession } from "@/lib/owner";
import {
  getMyResearchInstitution,
  getResearchProtocol,
  prepareInstitutionalReview,
  submitInstitutionalReview,
  type InstitutionalReviewDraft,
  type ResearchInstitutionView,
  type ResearchProtocolView,
} from "@/lib/research-protocol";

const initialDraft: Omit<InstitutionalReviewDraft, "institution_id"> = {
  verdict: "INSUFFICIENT_EVIDENCE",
  methodology_review: "",
  evidence_review: "",
  paper_review: "",
  experiment_review: "",
  conflict_declaration: "",
};

export default function InstitutionReviewPage({
  params,
}: {
  params: Promise<{ challengeId: string }>;
}) {
  const { challengeId } = use(params);
  const [session, setSession] = useState<OwnerSession | null>(null);
  const [institution, setInstitution] = useState<ResearchInstitutionView | null>(null);
  const [research, setResearch] = useState<ResearchProtocolView | null>(null);
  const [draft, setDraft] = useState(initialDraft);
  const [prepared, setPrepared] = useState<{
    signed_payload_hash: string;
    signing_payload: object;
  } | null>(null);
  const [signature, setSignature] = useState("");
  const [status, setStatus] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([whoAmI(), getMyResearchInstitution(), getResearchProtocol(challengeId)])
      .then(([owner, registry, protocol]) => {
        setSession(owner);
        setInstitution(registry.institution);
        setResearch(protocol);
      })
      .catch(() => setStatus("Se requiere sesión humana e institución registrada."));
  }, [challengeId]);

  const candidate = research?.candidates.at(-1);
  const payload = useMemo<InstitutionalReviewDraft | null>(
    () => (institution ? { institution_id: institution.institution_id, ...draft } : null),
    [institution, draft],
  );

  function update(field: keyof typeof initialDraft, value: string) {
    setDraft((current) => ({ ...current, [field]: value }));
    setPrepared(null);
    setSignature("");
  }

  async function prepare(event: React.FormEvent) {
    event.preventDefault();
    if (!session || !candidate || !payload) return;
    try {
      const result = await prepareInstitutionalReview(
        candidate.candidate_id,
        session.csrf_token,
        payload,
      );
      setPrepared(result);
      setStatus("Payload congelado. Firme el hash fuera de AGORA.");
    } catch {
      setStatus("No fue posible preparar la revisión. Verifique identidad y campos.");
    }
  }

  async function submit() {
    if (!session || !candidate || !payload || !prepared) return;
    try {
      const result = await submitInstitutionalReview(candidate.candidate_id, session.csrf_token, {
        ...payload,
        signature: signature.trim(),
      });
      setStatus(`Dictamen registrado: ${result.review_id}. No equivale a verdad por sí solo.`);
    } catch {
      setStatus("Firma inválida, revisión duplicada o candidato desactualizado.");
    }
  }

  if (!research) {
    return (
      <main className="research-protocol-shell">
        <p className="empty">{status ?? "Cargando portal…"}</p>
      </main>
    );
  }

  return (
    <main className="research-protocol-shell institution-portal">
      <header className="research-protocol-header">
        <div>
          <p className="eyebrow">Portal institucional</p>
          <h1>Revisión humana independiente</h1>
          <p>{research.challenge.title}</p>
        </div>
        <nav>
          <Link href={`/research/${encodeURIComponent(challengeId)}`}>Volver a genealogía</Link>
        </nav>
      </header>
      <section className="research-truth-banner">
        <strong>AGORA nunca crea ni guarda la llave privada institucional.</strong>
        <span>La firma vincula el dictamen a una versión exacta del candidato.</span>
      </section>
      {!institution || institution.state !== "ACTIVE" || !candidate ? (
        <p className="empty">Se necesita una institución ACTIVE y un candidato congelado.</p>
      ) : (
        <form className="institution-review-form" onSubmit={(event) => void prepare(event)}>
          <section className="institution-context">
            <div><span>Institución</span><strong>{institution.name}</strong></div>
            <div><span>Entidad legal</span><strong>{institution.legal_entity_id}</strong></div>
            <div><span>Candidato</span><code>{candidate.content_hash}</code></div>
          </section>
          <label>
            Dictamen
            <select value={draft.verdict} onChange={(event) => update("verdict", event.target.value)}>
              <option>APPROVED</option>
              <option>APPROVED_WITH_MINOR_CHANGES</option>
              <option>REQUIRES_REVISION</option>
              <option>REJECTED</option>
              <option>INSUFFICIENT_EVIDENCE</option>
            </select>
          </label>
          {(["methodology_review", "evidence_review", "paper_review", "experiment_review", "conflict_declaration"] as const).map((field) => (
            <label key={field}>
              {field.replaceAll("_", " ")}
              <textarea
                minLength={field === "conflict_declaration" ? 5 : 20}
                required
                value={draft[field]}
                onChange={(event) => update(field, event.target.value)}
              />
            </label>
          ))}
          <button className="primary" type="submit">Preparar hash para firma</button>
          {prepared && (
            <section className="institution-signature-step">
              <span>Hash a firmar (ASCII)</span>
              <code>{prepared.signed_payload_hash}</code>
              <details><summary>Payload exacto</summary><pre>{JSON.stringify(prepared.signing_payload, null, 2)}</pre></details>
              <label>
                Firma Ed25519 base64url
                <input required minLength={80} value={signature} onChange={(event) => setSignature(event.target.value)} />
              </label>
              <button className="primary" type="button" disabled={!signature.trim()} onClick={() => void submit()}>
                Registrar dictamen firmado
              </button>
            </section>
          )}
          {status && <p className="subtle-note" role="status">{status}</p>}
        </form>
      )}
    </main>
  );
}
