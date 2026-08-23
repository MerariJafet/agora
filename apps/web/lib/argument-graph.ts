// Deterministic radial layout for a bounded argument-graph neighborhood.
//
// Sprint 04 neighborhoods are capped at ~300 nodes server-side (ADR-0022),
// so a force-directed layout library is unnecessary weight and risk for what
// is, in practice, a small star/ring graph around one root claim. This
// dependency-free layout is the "justify a simpler implementation" path:
// deterministic (same graph -> same layout every render, easy to test),
// zero bundle cost, and sufficient for the bounded sizes AGORA ever ships to
// a browser by default.

import type { ClaimRelation, Neighborhood } from "@/lib/epistemic";

export interface GraphNode {
  claim_id: string;
  x: number;
  y: number;
}

export interface GraphLayout {
  nodes: GraphNode[];
  edges: (ClaimRelation & { x1: number; y1: number; x2: number; y2: number })[];
}

const RADIUS = 220;
const CENTER = 260;

export function layoutNeighborhood(neighborhood: Neighborhood): GraphLayout {
  const others = neighborhood.claims.filter((c) => c.claim_id !== neighborhood.root_claim_id);
  const nodes: GraphNode[] = [{ claim_id: neighborhood.root_claim_id, x: CENTER, y: CENTER }];
  others.forEach((claim, i) => {
    const angle = (2 * Math.PI * i) / Math.max(others.length, 1);
    nodes.push({
      claim_id: claim.claim_id,
      x: CENTER + Math.cos(angle) * RADIUS,
      y: CENTER + Math.sin(angle) * RADIUS,
    });
  });
  const byId = new Map(nodes.map((n) => [n.claim_id, n]));
  const edges = neighborhood.relations
    .map((relation) => {
      const from = byId.get(relation.source_claim_id);
      const to = byId.get(relation.target_claim_id);
      if (!from || !to) return null;
      return { ...relation, x1: from.x, y1: from.y, x2: to.x, y2: to.y };
    })
    .filter((e): e is NonNullable<typeof e> => e !== null);
  return { nodes, edges };
}

export const RELATION_COLOR: Record<string, string> = {
  supports: "#4ac48a",
  contradicts: "#e0596a",
  qualifies: "#d4a24a",
  refines: "#4aa3c4",
  depends_on: "#7b6ff0",
  questions: "#8a94ad",
  cites: "#3fbfb0",
};
