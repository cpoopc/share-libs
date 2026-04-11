/**
 * WebSocket Hook for IVA Log Tracer
 * 
 * Manages WebSocket connection lifecycle and message handling
 */

/// <reference types="vite/client" />

import { useEffect, useRef, useCallback, useState } from 'react';
import { useLogTracerStore } from '../store/logTracerStore';

export interface WSMessage {
    type: string;
    [key: string]: any;
}

export interface UseWebSocketOptions {
    sessionId: string;
    autoPoll?: boolean;
    pollInterval?: number;
    onMessage?: (message: WSMessage) => void;
    onConnect?: (connectionId: string) => void;
    onDisconnect?: () => void;
    onError?: (error: Event) => void;
}

export interface UseWebSocketReturn {
    isConnected: boolean;
    connectionId: string | null;
    send: (message: WSMessage) => void;
    subscribe: (components: string[]) => void;
    unsubscribe: (components: string[]) => void;
    sendTimeSync: (timestamp: string, sourcePanel: number) => void;
    reconnect: () => void;
    disconnect: () => void;
}

/**
 * Get WebSocket URL based on current environment
 */
function getWebSocketUrl(sessionId: string, autoPoll: boolean, pollInterval: number): string {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host;

    // In development, the backend runs on a different port
    // Check if we're proxied through nginx or running standalone
    const baseUrl = import.meta.env.DEV
        ? `ws://localhost:8190`  // Direct backend connection in dev
        : `${protocol}//${host}`;

    const params = new URLSearchParams();
    if (autoPoll) {
        params.set('auto_poll', 'true');
        params.set('poll_interval', pollInterval.toString());
    }

    const queryString = params.toString();
    return `${baseUrl}/api/ws/session/${sessionId}${queryString ? `?${queryString}` : ''}`;
}

export function useWebSocket({
    sessionId,
    autoPoll = false,
    pollInterval = 5,
    onMessage,
    onConnect,
    onDisconnect,
    onError,
}: UseWebSocketOptions): UseWebSocketReturn {
    const wsRef = useRef<WebSocket | null>(null);
    const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
    const [connectionId, setConnectionId] = useState<string | null>(null);
    const [isConnected, setIsConnected] = useState(false);

    // Store actions
    const {
        setConnected,
        appendComponentLogs,
        setTimeAnchor,
        addSubscription,
        removeSubscription,
    } = useLogTracerStore();

    // Connect to WebSocket
    const connect = useCallback(() => {
        if (!sessionId || wsRef.current?.readyState === WebSocket.OPEN) {
            return;
        }

        // Close existing connection if any
        if (wsRef.current) {
            wsRef.current.close();
        }

        const url = getWebSocketUrl(sessionId, autoPoll, pollInterval);
        const ws = new WebSocket(url);
        wsRef.current = ws;

        ws.onopen = () => {
            console.log('[LogTracer WS] Connected');
            setIsConnected(true);
        };

        ws.onmessage = (event) => {
            try {
                const message: WSMessage = JSON.parse(event.data);

                // Handle built-in message types
                switch (message.type) {
                    case 'connected':
                        setConnectionId(message.connection_id);
                        setConnected(true, message.connection_id);
                        onConnect?.(message.connection_id);
                        break;

                    case 'logs':
                        // Append logs to store
                        if (message.component && message.logs) {
                            appendComponentLogs(message.component, message.logs);
                        }
                        break;

                    case 'time_sync':
                        // Handle time sync from another client
                        if (message.timestamp && message.source_panel !== undefined) {
                            setTimeAnchor(
                                message.timestamp,
                                message.source_panel,
                                message.source_conn_id
                            );
                        }
                        break;

                    case 'subscribed':
                        message.components?.forEach((c: string) => addSubscription(c));
                        break;

                    case 'unsubscribed':
                        message.components?.forEach((c: string) => removeSubscription(c));
                        break;

                    case 'error':
                        console.error('[LogTracer WS] Error:', message.error);
                        break;

                    case 'pong':
                        // Ping response, ignore
                        break;
                }

                // Call custom handler
                onMessage?.(message);

            } catch (e) {
                console.error('[LogTracer WS] Failed to parse message:', e);
            }
        };

        ws.onclose = () => {
            console.log('[LogTracer WS] Disconnected');
            setIsConnected(false);
            setConnectionId(null);
            setConnected(false);
            onDisconnect?.();

            // Auto-reconnect after 3 seconds
            if (reconnectTimeoutRef.current) {
                clearTimeout(reconnectTimeoutRef.current);
            }
            reconnectTimeoutRef.current = setTimeout(() => {
                if (sessionId) {
                    console.log('[LogTracer WS] Attempting to reconnect...');
                    connect();
                }
            }, 3000);
        };

        ws.onerror = (error) => {
            console.error('[LogTracer WS] Error:', error);
            onError?.(error);
        };
    }, [sessionId, autoPoll, pollInterval, onConnect, onDisconnect, onError, onMessage]);

    // Send message
    const send = useCallback((message: WSMessage) => {
        if (wsRef.current?.readyState === WebSocket.OPEN) {
            wsRef.current.send(JSON.stringify(message));
        } else {
            console.warn('[LogTracer WS] Cannot send, not connected');
        }
    }, []);

    // Subscribe to components
    const subscribe = useCallback((components: string[]) => {
        send({ type: 'subscribe', components });
    }, [send]);

    // Unsubscribe from components
    const unsubscribe = useCallback((components: string[]) => {
        send({ type: 'unsubscribe', components });
    }, [send]);

    // Send time sync
    const sendTimeSync = useCallback((timestamp: string, sourcePanel: number) => {
        send({ type: 'time_sync', timestamp, source_panel: sourcePanel });
    }, [send]);

    // Reconnect
    const reconnect = useCallback(() => {
        if (wsRef.current) {
            wsRef.current.close();
        }
        connect();
    }, [connect]);

    // Disconnect
    const disconnect = useCallback(() => {
        if (reconnectTimeoutRef.current) {
            clearTimeout(reconnectTimeoutRef.current);
            reconnectTimeoutRef.current = null;
        }
        if (wsRef.current) {
            wsRef.current.close();
            wsRef.current = null;
        }
        setIsConnected(false);
        setConnectionId(null);
        setConnected(false);
    }, [setConnected]);

    // Connect on mount / session change
    useEffect(() => {
        if (sessionId) {
            connect();
        }

        return () => {
            if (reconnectTimeoutRef.current) {
                clearTimeout(reconnectTimeoutRef.current);
            }
            if (wsRef.current) {
                wsRef.current.close();
            }
        };
    }, [sessionId, connect]);

    // Ping keep-alive
    useEffect(() => {
        if (!isConnected) return;

        const pingInterval = setInterval(() => {
            send({ type: 'ping' });
        }, 30000); // Ping every 30 seconds

        return () => clearInterval(pingInterval);
    }, [isConnected, send]);

    return {
        isConnected,
        connectionId,
        send,
        subscribe,
        unsubscribe,
        sendTimeSync,
        reconnect,
        disconnect,
    };
}
