import { Suspense } from "react";
import { IsometricWorldScene } from "@/world/isometric-scene";

export default function WorldReplayPage() {
  return (
    <Suspense fallback={null}>
      <IsometricWorldScene mode="replay" targetId="central" />
    </Suspense>
  );
}
