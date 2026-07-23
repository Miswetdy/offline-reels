"use client";

import { useNetworkStatus } from "../hooks/use-network-status";

type NetworkStatusIndicatorProps = {
  offlineMessage: string;
  onlineMessage?: string;
};

export function NetworkStatusIndicator({ offlineMessage, onlineMessage = "Онлайн" }: NetworkStatusIndicatorProps) {
  const isOnline = useNetworkStatus();

  return (
    <p aria-live="polite" data-testid="network-status">
      {isOnline ? onlineMessage : offlineMessage}
    </p>
  );
}
