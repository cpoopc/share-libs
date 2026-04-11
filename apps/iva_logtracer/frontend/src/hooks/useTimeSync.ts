/**
 * Time Sync Hook for IVA Log Tracer
 * 
 * Manages time synchronization across multiple log panels
 */

import { useCallback, useEffect, useRef } from 'react';
import { useLogTracerStore, LogEntry } from '../store/logTracerStore';

export interface UseTimeSyncOptions {
    panelIndex: number;
    panelId: string;
    logs: LogEntry[];
    listRef: React.RefObject<any>; // VariableSizeList ref
    onSyncScroll?: (index: number) => void;
}

export interface UseTimeSyncReturn {
    handleLogClick: (log: LogEntry, index: number) => void;
    isSourcePanel: boolean;
}

/**
 * Binary search to find the log index closest to a target timestamp
 */
function findNearestLogIndex(logs: LogEntry[], targetTimestamp: string): number {
    if (logs.length === 0) return 0;

    const target = new Date(targetTimestamp).getTime();
    let left = 0;
    let right = logs.length - 1;

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

export function useTimeSync({
    panelIndex,
    panelId,
    logs,
    listRef,
    onSyncScroll,
}: UseTimeSyncOptions): UseTimeSyncReturn {
    const {
        timeAnchor,
        isTimeSyncEnabled,
        setTimeAnchor
    } = useLogTracerStore();

    const lastSyncedTimestamp = useRef<string | null>(null);

    // Check if this panel is the source of the current sync
    const isSourcePanel = timeAnchor.sourcePanelId === panelId;

    // Handle log click - set time anchor
    const handleLogClick = useCallback((log: LogEntry, _index: number) => {
        if (!isTimeSyncEnabled) return;

        // Set this panel as the source and broadcast the timestamp
        setTimeAnchor(log.timestamp, panelIndex, panelId);
    }, [isTimeSyncEnabled, panelIndex, panelId, setTimeAnchor]);

    // Sync scroll when time anchor changes (if not the source panel)
    useEffect(() => {
        if (!isTimeSyncEnabled) return;
        if (!timeAnchor.timestamp) return;
        if (isSourcePanel) return; // Don't sync the source panel
        if (logs.length === 0) return;
        if (timeAnchor.timestamp === lastSyncedTimestamp.current) return;

        // Find the nearest log index
        const targetIndex = findNearestLogIndex(logs, timeAnchor.timestamp);
        lastSyncedTimestamp.current = timeAnchor.timestamp;

        // Scroll to the target index
        if (listRef.current?.scrollToItem) {
            listRef.current.scrollToItem(targetIndex, 'center');
        }

        onSyncScroll?.(targetIndex);
    }, [timeAnchor, isTimeSyncEnabled, isSourcePanel, logs, listRef, onSyncScroll]);

    return {
        handleLogClick,
        isSourcePanel,
    };
}

/**
 * Higher-level hook for managing time sync with WebSocket
 */
export function useTimeSyncWithWs({
    panelIndex,
    panelId,
    logs,
    listRef,
    sendTimeSync,
    onSyncScroll,
}: UseTimeSyncOptions & {
    sendTimeSync?: (timestamp: string, sourcePanel: number) => void;
}): UseTimeSyncReturn {
    const {
        timeAnchor,
        isTimeSyncEnabled,
        setTimeAnchor
    } = useLogTracerStore();

    const lastSyncedTimestamp = useRef<string | null>(null);
    const isSourcePanel = timeAnchor.sourcePanelId === panelId;

    // Handle log click - set time anchor and broadcast via WS
    const handleLogClick = useCallback((log: LogEntry, _index: number) => {
        if (!isTimeSyncEnabled) return;

        // Set local time anchor
        setTimeAnchor(log.timestamp, panelIndex, panelId);

        // Broadcast to other clients via WebSocket
        sendTimeSync?.(log.timestamp, panelIndex);
    }, [isTimeSyncEnabled, panelIndex, panelId, setTimeAnchor, sendTimeSync]);

    // Sync scroll when time anchor changes
    useEffect(() => {
        if (!isTimeSyncEnabled) return;
        if (!timeAnchor.timestamp) return;
        if (isSourcePanel) return;
        if (logs.length === 0) return;
        if (timeAnchor.timestamp === lastSyncedTimestamp.current) return;

        const targetIndex = findNearestLogIndex(logs, timeAnchor.timestamp);
        lastSyncedTimestamp.current = timeAnchor.timestamp;

        if (listRef.current?.scrollToItem) {
            listRef.current.scrollToItem(targetIndex, 'center');
        }

        onSyncScroll?.(targetIndex);
    }, [timeAnchor, isTimeSyncEnabled, isSourcePanel, logs, listRef, onSyncScroll]);

    return {
        handleLogClick,
        isSourcePanel,
    };
}
