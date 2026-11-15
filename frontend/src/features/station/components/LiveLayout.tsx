import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { Arm } from "../api/types";
import { CameraGrid } from "./CameraGrid";
import { JointPanel } from "./JointPanel";
import { MotorHealthPanel } from "./MotorHealthPanel";

/**
 * Running view shared by Teleop / Record / Replay / Run (§6.5): header (timer + controls) first,
 * then cameras and motor health on the left, joints on the right. Narrow screens stack cameras,
 * health, joints.
 */
export function LiveLayout({
  header,
  arms,
  chart = false,
  cameraNames,
}: {
  header: ReactNode;
  arms?: Arm[];
  chart?: boolean;
  cameraNames?: string[];
}) {
  const { t } = useTranslation("station");
  return (
    <div className="flex flex-col gap-4">
      {header}
      <div className="grid gap-4 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <div className="flex min-w-0 flex-col gap-4">
          <CameraGrid {...(cameraNames ? { names: cameraNames } : {})} />
          <Card>
            <CardHeader>
              <CardTitle>{t("health.title")}</CardTitle>
            </CardHeader>
            <CardContent>
              <MotorHealthPanel {...(arms ? { arms } : {})} />
            </CardContent>
          </Card>
        </div>
        <Card className="min-w-0 self-start">
          <CardHeader>
            <CardTitle>{t("joints.title")}</CardTitle>
          </CardHeader>
          <CardContent>
            <JointPanel chart={chart} />
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
