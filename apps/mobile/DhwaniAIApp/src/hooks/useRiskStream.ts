import { useEffect } from 'react';
import { wsService, ConnectionState } from '../services/websocket/wsService';
import { useRiskStore } from '../store/riskStore';
import { SessionStatus } from '../types';

const STATUS_FOR_CONNECTION: Record<ConnectionState, SessionStatus> = {
  idle: 'idle',
  connecting: 'connecting',
  open: 'monitoring',
  reconnecting: 'reconnecting',
  closed: 'ended',
  failed: 'error',
};

/**
 * Bridges the WebSocket to the Zustand dashboard store.
 *
 * Every message is handed to `applyEvent`, which owns de-duplication, ordering
 * and validation. This hook only wires the two together and mirrors the
 * transport's connection state onto `sessionStatus`.
 */
export function useRiskStream(sessionId: string | undefined) {
  const applyEvent = useRiskStore(s => s.applyEvent);
  const setSessionStatus = useRiskStore(s => s.setSessionStatus);

  useEffect(() => {
    if (!sessionId) {
      return;
    }

    const removeEvents = wsService.addHandler(applyEvent);
    const removeState = wsService.addStateHandler(connection => {
      setSessionStatus(STATUS_FOR_CONNECTION[connection] ?? 'idle');
    });

    return () => {
      removeEvents();
      removeState();
    };
  }, [sessionId, applyEvent, setSessionStatus]);
}
