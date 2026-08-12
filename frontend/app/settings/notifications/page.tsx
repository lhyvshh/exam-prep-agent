import React from "react";

import { NotificationSettingsWorkspace } from "@/components/notifications/notification-settings-workspace";
import { AppFrame } from "@/components/shared/app-frame";

export default function NotificationSettingsPage(): JSX.Element {
  return (
    <AppFrame
      currentSlug="notifications"
      eyebrow="Settings"
      title="Notifications"
      description="Opt-in reminder controls for the Study Coach. Email delivery is intentionally off until a user enables it."
      showContextSelector={false}
    >
      <NotificationSettingsWorkspace />
    </AppFrame>
  );
}
