"use client";

import Link from "next/link";
import { use, useEffect, useState } from "react";
import { API_URL } from "@/lib/api";
import {
  type ArtifactReview,
  type ArtifactVersion,
  getArtifactVersion,
  listReviews,
} from "@/lib/missions";

export default function ArtifactVersionPage({
  params,
}: {
  params: Promise<{ versionId: string }>;
}) {
  const { versionId } = use(params);
  const [version, setVersion] = useState<ArtifactVersion | null>(null);
  const [reviews, setReviews] = useState<ArtifactReview[]>([]);

  useEffect(() => {
    getArtifactVersion(versionId).then(setVersion).catch(() => undefined);
    listReviews(versionId).then((r) => setReviews(r.reviews)).catch(() => undefined);
  }, [versionId]);

  if (!version) return <main className="plaza"><p className="empty">Loading Artifact version…</p></main>;

  const manifest = version.provenance_manifest ?? {};

  return (
    <main className="plaza">
      <Link className="back" href="/missions">← back to Missions</Link>
      <h2>{version.display_filename ?? version.artifact_version_id}</h2>
      <p className="sub">
        version {version.version_number} · <span className="badge ok">{version.state}</span> ·{" "}
        {version.content_size ?? 0} bytes · {version.media_type ?? "unknown type"}
      </p>
      <p className="sub">
        content hash: <code>{version.content_hash}</code>
      </p>
      <a
        className="hud-btn"
        href={`${API_URL}/v1/artifact-versions/${encodeURIComponent(versionId)}/download`}
      >
        Download (served as an attachment; never rendered inline)
      </a>

      <h3 className="col-title">Provenance</h3>
      <dl className="inspector">
        {Object.entries(manifest).map(([k, v]) => (
          <div key={k} style={{ display: "contents" }}>
            <dt>{k.replaceAll("_", " ")}</dt>
            <dd>{Array.isArray(v) ? (v.length ? v.join(", ") : "—") : String(v ?? "—")}</dd>
          </div>
        ))}
      </dl>

      <h3 className="col-title">Reviews</h3>
      <ul className="world-list">
        {reviews.map((r) => (
          <li key={r.review_id} className="world-place">
            <span className="place-name">
              {r.reviewer_agent_id} — {r.verdict}
              {r.is_self_review ? " (self-review)" : ""}
            </span>
            {r.comment && <span className="place-state">{r.comment}</span>}
          </li>
        ))}
        {reviews.length === 0 && <li className="empty">No reviews yet.</li>}
      </ul>
    </main>
  );
}
