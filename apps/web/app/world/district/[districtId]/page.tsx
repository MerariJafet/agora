import { Suspense, use } from "react";
import { IsometricWorldScene } from "@/world/isometric-scene";

export default function DistrictWorldPage({
  params,
}: {
  params: Promise<{ districtId: string }>;
}) {
  const { districtId } = use(params);
  return (
    <Suspense fallback={null}>
      <IsometricWorldScene mode="district" targetId={districtId} />
    </Suspense>
  );
}
