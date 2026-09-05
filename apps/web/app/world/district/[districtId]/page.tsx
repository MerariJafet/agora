import { use } from "react";
import { IsometricWorldScene } from "@/world/isometric-scene";

export default function DistrictWorldPage({
  params,
}: {
  params: Promise<{ districtId: string }>;
}) {
  const { districtId } = use(params);
  return <IsometricWorldScene mode="district" targetId={districtId} />;
}
