/**
 * IVA Log Tracer Store (Zustand)
 * 
 * Central state management for:
 * - Session and connection state
 * - Logs cache per component
 * - Time sync anchor
 * - WebSocket connection
 */

import { create } from 'zustand';
import { devtools } from 'zustand/middleware';

// Types
export interface LogEntry {
    timestamp: string;
    type: 'out' | 'err';
    message: string;
    source: string;
    level?: string;
    logger?: string;
}

export interface TimeAnchor {
    timestamp: string | null;
    sourcePanel: number | null;
    sourcePanelId: string | null;
}

export interface ComponentLogs {
    logs: LogEntry[];
    isLoading: boolean;
    error: string | null;
    lastFetch: number | null;
}

export interface LogTracerState {
    // Session state
    sessionId: string;
    connectionId: string | null;
    isConnected: boolean;

    // Logs cache per component
    componentLogs: Record<string, ComponentLogs>;

    // Time sync
    timeAnchor: TimeAnchor;
    isTimeSyncEnabled: boolean;

    // Subscribed components
    subscribedComponents: Set<string>;

    // Actions
    setSessionId: (sessionId: string) => void;
    setConnected: (isConnected: boolean, connectionId?: string) => void;

    // Logs actions
    setComponentLogs: (component: string, logs: LogEntry[]) => void;
    appendComponentLogs: (component: string, logs: LogEntry[]) => void;
    setComponentLoading: (component: string, isLoading: boolean) => void;
    setComponentError: (component: string, error: string | null) => void;
    clearComponentLogs: (component: string) => void;
    clearAllLogs: () => void;

    // Time sync actions
    setTimeAnchor: (timestamp: string, sourcePanel: number, sourcePanelId: string) => void;
    clearTimeAnchor: () => void;
    setTimeSyncEnabled: (enabled: boolean) => void;

    // Subscription actions
    addSubscription: (component: string) => void;
    removeSubscription: (component: string) => void;

    // Helpers
    getScrollIndexForTimestamp: (component: string, targetTimestamp: string) => number;
}

/**
 * Binary search to find the log index closest to a target timestamp
 */
function findNearestLogIndex(logs: LogEntry[], targetTimestamp: string): number {
    if (logs.length === 0) return 0;

    const target = new Date(targetTimestamp).getTime();
    let left = 0;
    let right = logs.length - 1;

    // Binary search for the closest timestamp
    while (left < right) {
        const mid = Math.floor((left + right) / 2);
        const midTime = new Date(logs[mid].timestamp).getTime();

        if (midTime < target) {
            left = mid + 1;
        } else {
            right = mid;
        }
    }

    // Check if the previous index is closer
    if (left > 0) {
        const leftTime = new Date(logs[left].timestamp).getTime();
        const prevTime = new Date(logs[left - 1].timestamp).getTime();

        if (Math.abs(prevTime - target) < Math.abs(leftTime - target)) {
            return left - 1;
        }
    }

    return left;
}

export const useLogTracerStore = create<LogTracerState>()(
    devtools(
        (set, get) => ({
            // Initial state
            sessionId: '',
            connectionId: null,
            isConnected: false,

            componentLogs: {},

            timeAnchor: {
                timestamp: null,
                sourcePanel: null,
                sourcePanelId: null,
            },
            isTimeSyncEnabled: false,

            subscribedComponents: new Set(),

            // Session actions
            setSessionId: (sessionId) => set({ sessionId }),

            setConnected: (isConnected, connectionId) => set({
                isConnected,
                connectionId: connectionId ?? null
            }),

            // Logs actions
            setComponentLogs: (component, logs) => set((state) => ({
                componentLogs: {
                    ...state.componentLogs,
                    [component]: {
                        logs,
                        isLoading: false,
                        error: null,
                        lastFetch: Date.now(),
                    },
                },
            })),

            appendComponentLogs: (component, newLogs) => set((state) => {
                const existing = state.componentLogs[component]?.logs ?? [];
                // Merge and sort by timestamp
                const merged = [...existing, ...newLogs].sort(
                    (a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime()
                );
                // Deduplicate by timestamp + message
                const seen = new Set<string>();
                const deduplicated = merged.filter((log) => {
                    const key = `${log.timestamp}:${log.message}`;
                    if (seen.has(key)) return false;
                    seen.add(key);
                    return true;
                });

                return {
                    componentLogs: {
                        ...state.componentLogs,
                        [component]: {
                            logs: deduplicated,
                            isLoading: false,
                            error: null,
                            lastFetch: Date.now(),
                        },
                    },
                };
            }),

            setComponentLoading: (component, isLoading) => set((state) => ({
                componentLogs: {
                    ...state.componentLogs,
                    [component]: {
                        ...(state.componentLogs[component] ?? { logs: [], error: null, lastFetch: null }),
                        isLoading,
                    },
                },
            })),

            setComponentError: (component, error) => set((state) => ({
                componentLogs: {
                    ...state.componentLogs,
                    [component]: {
                        ...(state.componentLogs[component] ?? { logs: [], isLoading: false, lastFetch: null }),
                        error,
                    },
                },
            })),

            clearComponentLogs: (component) => set((state) => {
                const { [component]: _, ...rest } = state.componentLogs;
                return { componentLogs: rest };
            }),

            clearAllLogs: () => set({ componentLogs: {} }),

            // Time sync actions
            setTimeAnchor: (timestamp, sourcePanel, sourcePanelId) => set({
                timeAnchor: {
                    timestamp,
                    sourcePanel,
                    sourcePanelId,
                },
            }),

            clearTimeAnchor: () => set({
                timeAnchor: {
                    timestamp: null,
                    sourcePanel: null,
                    sourcePanelId: null,
                },
            }),

            setTimeSyncEnabled: (enabled) => set({ isTimeSyncEnabled: enabled }),

            // Subscription actions
            addSubscription: (component) => set((state) => ({
                subscribedComponents: new Set([...state.subscribedComponents, component]),
            })),

            removeSubscription: (component) => set((state) => {
                const newSet = new Set(state.subscribedComponents);
                newSet.delete(component);
                return { subscribedComponents: newSet };
            }),

            // Helpers
            getScrollIndexForTimestamp: (component, targetTimestamp) => {
                const state = get();
                const logs = state.componentLogs[component]?.logs ?? [];
                return findNearestLogIndex(logs, targetTimestamp);
            },
        }),
        { name: 'iva-logtracer-store' }
    )
);
