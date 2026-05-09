import { useEffect, useRef } from 'react';
import { io, Socket } from 'socket.io-client';
import type { WsMessage } from '../types';

interface UseRunSocketOptions {
  runId: number | null;
  onMessage: (msg: WsMessage) => void;
}

export default function useRunSocket({ runId, onMessage }: UseRunSocketOptions) {
  const socketRef = useRef<Socket | null>(null);
  const onMessageRef = useRef(onMessage);
  onMessageRef.current = onMessage;

  useEffect(() => {
    if (!runId) return;

    const socket = io('/', {
      path: '/ws/socket.io',
      transports: ['websocket', 'polling'],
    });
    socketRef.current = socket;

    socket.on('connect', () => {
      socket.emit('join_run', { run_id: runId });
    });

    socket.on('run_event', (msg: WsMessage) => {
      if (msg.run_id === runId) {
        onMessageRef.current(msg);
      }
    });

    socket.on('disconnect', () => {
      // will auto-reconnect
    });

    return () => {
      socket.emit('leave_run', { run_id: runId });
      socket.disconnect();
      socketRef.current = null;
    };
  }, [runId]);
}
