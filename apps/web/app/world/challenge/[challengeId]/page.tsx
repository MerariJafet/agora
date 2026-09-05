import { Suspense, use } from "react";
import { IsometricWorldScene } from "@/world/isometric-scene";

export default function ChallengeWorldPage({
  params,
}: {
  params: Promise<{ challengeId: string }>;
}) {
  const { challengeId } = use(params);
  return (
    <Suspense fallback={null}>
      <IsometricWorldScene mode="challenge" targetId={challengeId} />
    </Suspense>
  );
}
