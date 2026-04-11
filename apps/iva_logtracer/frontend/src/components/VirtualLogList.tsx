/**
 * VirtualLogList Component
 * 
 * High-performance virtualized log viewer using react-window.
 * Supports:
 * - Variable row heights for multi-line logs
 * - Time sync click handling
 * - Syntax highlighting for log levels
 */

import React, { useRef, useCallback, useEffect, useMemo, forwardRef, useImperativeHandle } from 'react';
import { VariableSizeList as List } from 'react-window';
import { LogEntry } from '../store/logTracerStore';
import { cn } from '@cptools/ui';

// Estimate line height based on content
const LINE_HEIGHT = 20;
const MIN_ROW_HEIGHT = 28;
const CHARS_PER_LINE = 120;
const PADDING = 8;

export interface VirtualLogListProps {
    logs: LogEntry[];
    height: number;
    width?: number | string;
    searchQuery?: string;
    useRegex?: boolean;
    typeFilter?: 'all' | 'out' | 'err';
    levels?: string[];
    onLogClick?: (log: LogEntry, index: number) => void;
    highlightIndex?: number | null;
    className?: string;
}

export interface VirtualLogListRef {
    scrollToItem: (index: number, align?: 'auto' | 'smart' | 'center' | 'end' | 'start') => void;
    scrollToTop: () => void;
    scrollToBottom: () => void;
}

/**
 * Escape special regex characters in a string
 */
function escapeRegex(str: string): string {
    return str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

/**
 * Check if a log matches the search query
 */
function matchesSearch(log: LogEntry, query: string, useRegex: boolean): boolean {
    if (!query) return true;

    try {
        if (useRegex) {
            const regex = new RegExp(query, 'i');
            return regex.test(log.message);
        } else {
            return log.message.toLowerCase().includes(query.toLowerCase());
        }
    } catch {
        return false;
    }
}

/**
 * Filter logs based on type and level
 */
function filterLogs(
    logs: LogEntry[],
    typeFilter: 'all' | 'out' | 'err',
    levels: string[],
    searchQuery: string,
    useRegex: boolean
): LogEntry[] {
    return logs.filter((log) => {
        // Type filter
        if (typeFilter !== 'all' && log.type !== typeFilter) {
            return false;
        }

        // Level filter
        if (levels.length > 0 && log.level && !levels.includes(log.level)) {
            return false;
        }

        // Search filter
        if (searchQuery && !matchesSearch(log, searchQuery, useRegex)) {
            return false;
        }

        return true;
    });
}

/**
 * Highlight search matches in text
 */
function highlightMatches(text: string, query: string, useRegex: boolean): React.ReactNode {
    if (!query) return text;

    try {
        const regex = useRegex ? new RegExp(`(${query})`, 'gi') : new RegExp(`(${escapeRegex(query)})`, 'gi');
        const parts = text.split(regex);

        return parts.map((part, i) => {
            if (regex.test(part)) {
                return (
                    <mark key={i} className="bg-yellow-400/40 text-inherit px-0.5 rounded">
                        {part}
                    </mark>
                );
            }
            return part;
        });
    } catch {
        return text;
    }
}

/**
 * Get log level color class
 */
function getLevelColorClass(level?: string): string {
    switch (level?.toUpperCase()) {
        case 'ERROR':
            return 'text-red-400';
        case 'WARN':
        case 'WARNING':
            return 'text-yellow-400';
        case 'INFO':
            return 'text-blue-400';
        case 'DEBUG':
            return 'text-gray-400';
        default:
            return 'text-foreground';
    }
}

/**
 * Log row component
 */
interface LogRowProps {
    log: LogEntry;
    index: number;
    style: React.CSSProperties;
    searchQuery?: string;
    useRegex?: boolean;
    isHighlighted?: boolean;
    onClick?: (log: LogEntry, index: number) => void;
}

const LogRow = React.memo(function LogRow({
    log,
    index,
    style,
    searchQuery,
    useRegex,
    isHighlighted,
    onClick,
}: LogRowProps) {
    const timestamp = useMemo(() => {
        try {
            const date = new Date(log.timestamp);
            if (isNaN(date.getTime())) {
                return log.timestamp;
            }
            return date.toLocaleTimeString('en-US', {
                hour12: false,
                hour: '2-digit',
                minute: '2-digit',
                second: '2-digit',
                fractionalSecondDigits: 3,
            } as any);
        } catch {
            return log.timestamp;
        }
    }, [log.timestamp]);

    const levelColorClass = getLevelColorClass(log.level);

    return (
        <div
            style={style}
            className={cn(
                'flex items-start gap-2 px-2 py-1 font-mono text-xs border-b border-border/50 cursor-pointer hover:bg-muted/50 transition-colors',
                isHighlighted && 'bg-primary/20 border-primary/50',
                log.type === 'err' && 'bg-red-500/5'
            )}
            onClick={() => onClick?.(log, index)}
        >
            {/* Timestamp */}
            <span className="text-muted-foreground shrink-0 select-none">
                {timestamp}
            </span>

            {/* Level badge */}
            {log.level && (
                <span className={cn('shrink-0 w-12 text-center', levelColorClass)}>
                    [{log.level.slice(0, 4)}]
                </span>
            )}

            {/* Message */}
            <span className={cn('flex-1 whitespace-pre-wrap break-all', levelColorClass)}>
                {searchQuery
                    ? highlightMatches(log.message, searchQuery, useRegex || false)
                    : log.message
                }
            </span>
        </div>
    );
});

/**
 * VirtualLogList component with imperative handle
 */
export const VirtualLogList = forwardRef<VirtualLogListRef, VirtualLogListProps>(
    function VirtualLogList(
        {
            logs,
            height,
            width = '100%',
            searchQuery = '',
            useRegex = false,
            typeFilter = 'all',
            levels = [],
            onLogClick,
            highlightIndex,
            className,
        },
        ref
    ) {
        const listRef = useRef<List>(null);
        const rowHeights = useRef<Map<number, number>>(new Map());

        // Filter logs
        const filteredLogs = useMemo(
            () => filterLogs(logs, typeFilter, levels, searchQuery, useRegex),
            [logs, typeFilter, levels, searchQuery, useRegex]
        );

        // Estimate row height based on message length
        const getItemSize = useCallback((index: number): number => {
            const cached = rowHeights.current.get(index);
            if (cached) return cached;

            const log = filteredLogs[index];
            if (!log) return MIN_ROW_HEIGHT;

            // Estimate lines based on message length
            const lines = Math.ceil(log.message.length / CHARS_PER_LINE);
            const estimatedHeight = Math.max(MIN_ROW_HEIGHT, lines * LINE_HEIGHT + PADDING);

            rowHeights.current.set(index, estimatedHeight);
            return estimatedHeight;
        }, [filteredLogs]);

        // Reset row heights when logs change
        useEffect(() => {
            rowHeights.current.clear();
            listRef.current?.resetAfterIndex(0);
        }, [filteredLogs]);

        // Expose imperative methods
        useImperativeHandle(ref, () => ({
            scrollToItem: (index: number, align: 'auto' | 'smart' | 'center' | 'end' | 'start' = 'center') => {
                listRef.current?.scrollToItem(index, align);
            },
            scrollToTop: () => {
                listRef.current?.scrollToItem(0, 'start');
            },
            scrollToBottom: () => {
                listRef.current?.scrollToItem(filteredLogs.length - 1, 'end');
            },
        }), [filteredLogs.length]);

        // Render row
        const Row = useCallback(
            ({ index, style }: { index: number; style: React.CSSProperties }) => {
                const log = filteredLogs[index];
                if (!log) return null;

                return (
                    <LogRow
                        log={log}
                        index={index}
                        style={style}
                        searchQuery={searchQuery}
                        useRegex={useRegex}
                        isHighlighted={highlightIndex === index}
                        onClick={onLogClick}
                    />
                );
            },
            [filteredLogs, searchQuery, useRegex, highlightIndex, onLogClick]
        );

        if (filteredLogs.length === 0) {
            return (
                <div className={cn('flex items-center justify-center h-full text-muted-foreground', className)}>
                    {logs.length === 0 ? 'No logs available' : 'No logs match the current filters'}
                </div>
            );
        }

        return (
            <List
                ref={listRef}
                height={height}
                width={width}
                itemCount={filteredLogs.length}
                itemSize={getItemSize}
                className={cn('scrollbar-thin scrollbar-thumb-muted scrollbar-track-transparent', className)}
                overscanCount={10}
            >
                {Row}
            </List>
        );
    }
);

export default VirtualLogList;
