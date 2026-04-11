import { useState, useCallback, useEffect, useRef } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
    Button, Badge, Input,
    LogViewerToolbar,
    LogViewerMultiPanel,
    LogViewerPageHeader,
    LogViewerPageFooter,
    SavedFilter,
} from '@cptools/ui'
import { Search, Clock, Activity } from 'lucide-react'
import * as logsApi from '../api/logs'
import { VirtualLogList } from '../components/VirtualLogList'
import { useWebSocket } from '../hooks/useWebSocket'
import { useTimeSync } from '../hooks/useTimeSync'
import { useContainerSize } from '../hooks/useContainerSize'
import { useLogTracerStore } from '../store/logTracerStore'

const SAVED_FILTERS_KEY = 'iva-logtracer-saved-filters'

export function LogTracerPage() {
    const [searchParams, setSearchParams] = useSearchParams()

    // Session/search state
    const [sessionId, setSessionId] = useState(searchParams.get('sessionId') || '')
    const [timeRange, setTimeRange] = useState(searchParams.get('timeRange') || '1h')

    // Filter state
    const [logFilter, setLogFilter] = useState<'all' | 'out' | 'err'>((searchParams.get('filter') as any) || 'all')
    const [logLevels, setLogLevels] = useState<string[]>([])
    const [searchQuery, setSearchQuery] = useState(searchParams.get('q') || '')
    const [useRegex, setUseRegex] = useState(searchParams.get('regex') === 'true')
    const [isSyncMode, setIsSyncMode] = useState(false)
    const [isTimeSync, setIsTimeSync] = useState(false)
    const [syncTimestamp, setSyncTimestamp] = useState<string | null>(null)

    // Panel state
    const [panels, setPanels] = useState<string[]>(['assistant_runtime'])
    const [focusedPanel, setFocusedPanel] = useState<number | null>(null)

    // WebSocket connection
    const { isConnected, subscribe } = useWebSocket({
        sessionId,
        autoPoll: true,
        onConnect: () => {
            // Re-subscribe to current panels on reconnect
            if (panels.length > 0) {
                subscribe(panels)
            }
        }
    })

    // Store actions
    const {
        setTimeSyncEnabled,
        setSessionId: setStoreSessionId,
    } = useLogTracerStore()

    // Sync session ID to store
    useEffect(() => {
        setStoreSessionId(sessionId)
    }, [sessionId, setStoreSessionId])

    // Sync time sync enabled state
    useEffect(() => {
        setTimeSyncEnabled(isTimeSync)
    }, [isTimeSync, setTimeSyncEnabled])

    // Subscription management
    useEffect(() => {
        if (isConnected && panels.length > 0) {
            subscribe(panels)
        }
        return () => {
            // Optional: unsubscribe all on unmount or session change
            // But usually fine to just leave them until connection closes
        }
    }, [panels, isConnected, subscribe])

    // Saved filters
    const [savedFilters, setSavedFilters] = useState<SavedFilter[]>(() => {
        try {
            const stored = localStorage.getItem(SAVED_FILTERS_KEY)
            return stored ? JSON.parse(stored) : []
        } catch {
            return []
        }
    })

    // Sync state to URL
    useEffect(() => {
        const params = new URLSearchParams(searchParams)

        if (sessionId) params.set('sessionId', sessionId)
        else params.delete('sessionId')

        if (timeRange && timeRange !== '1h') params.set('timeRange', timeRange)
        else if (timeRange === '1h') params.delete('timeRange')

        if (searchQuery) params.set('q', searchQuery)
        else params.delete('q')

        if (useRegex) params.set('regex', 'true')
        else params.delete('regex')

        if (logFilter && logFilter !== 'all') params.set('filter', logFilter)
        else params.delete('filter')

        setSearchParams(params, { replace: true })
    }, [sessionId, timeRange, searchQuery, useRegex, logFilter])

    const toggleLogLevel = (level: string) => {
        setLogLevels(prev =>
            prev.includes(level) ? prev.filter(l => l !== level) : [...prev, level]
        )
    }

    const saveFilters = useCallback((filters: SavedFilter[]) => {
        setSavedFilters(filters)
        localStorage.setItem(SAVED_FILTERS_KEY, JSON.stringify(filters))
    }, [])

    const handleSaveCurrentFilter = () => {
        if (!searchQuery.trim()) return
        const newFilter: SavedFilter = {
            id: Date.now().toString(),
            name: searchQuery.slice(0, 20) + (searchQuery.length > 20 ? '...' : ''),
            query: searchQuery,
            isRegex: useRegex,
        }
        saveFilters([...savedFilters, newFilter])
    }

    const handleApplyFilter = (filter: SavedFilter) => {
        setSearchQuery(filter.query)
        setUseRegex(filter.isRegex)
    }

    const handleDeleteFilter = (id: string) => {
        saveFilters(savedFilters.filter(f => f.id !== id))
    }

    const addPanel = () => {
        if (panels.length >= 4) return
        const availableComponent = logsApi.COMPONENTS.find(c => !panels.includes(c.id))
        if (availableComponent) {
            setPanels([...panels, availableComponent.id])
        } else if (logsApi.COMPONENTS.length > 0) {
            setPanels([...panels, logsApi.COMPONENTS[0].id])
        }
    }

    const removePanel = (index: number) => {
        if (panels.length <= 1) return
        setPanels(panels.filter((_, i) => i !== index))
    }

    return (
        <div className="flex flex-col h-full">
            {/* Header */}
            <LogViewerPageHeader
                title="IVA Log Tracer"
                panelCount={panels.length}
                maxPanels={4}
                onAddPanel={addPanel}
            >
                {/* Session ID Input */}
                <div className="flex items-center gap-2">
                    <Search className="h-4 w-4 text-muted-foreground" />
                    <Input
                        type="text"
                        placeholder="Session ID (s-xxx)"
                        value={sessionId}
                        onChange={(e) => setSessionId(e.target.value)}
                        className="h-8 w-48 text-sm"
                    />
                </div>

                {/* Time Range Selector */}
                <div className="flex items-center gap-1">
                    <Clock className="h-4 w-4 text-muted-foreground" />
                    <select
                        value={timeRange}
                        onChange={(e) => setTimeRange(e.target.value)}
                        className="h-8 px-2 text-sm border rounded bg-background"
                    >
                        <option value="15m">Last 15 min</option>
                        <option value="1h">Last 1 hour</option>
                        <option value="6h">Last 6 hours</option>
                        <option value="24h">Last 24 hours</option>
                        <option value="7d">Last 7 days</option>
                    </select>
                </div>
            </LogViewerPageHeader>

            {/* Search & Filter Toolbar */}
            <LogViewerToolbar
                logFilter={logFilter}
                onLogFilterChange={setLogFilter}
                logLevels={logLevels}
                onLogLevelToggle={toggleLogLevel}
                searchQuery={searchQuery}
                onSearchQueryChange={setSearchQuery}
                useRegex={useRegex}
                onUseRegexChange={setUseRegex}
                isSyncMode={isSyncMode}
                onSyncModeChange={setIsSyncMode}
                isTimeSync={isTimeSync}
                onTimeSyncChange={setIsTimeSync}
                savedFilters={savedFilters}
                onSaveFilter={handleSaveCurrentFilter}
                onApplyFilter={handleApplyFilter}
                onDeleteFilter={handleDeleteFilter}
            />

            {/* Multi-Panel Log View */}
            <LogViewerMultiPanel
                panels={panels}
                focusedPanel={focusedPanel}
                onFocusPanel={setFocusedPanel}
                renderPanel={(componentId, index) => (
                    <IVALogPanel
                        key={`${componentId}-${index}`}
                        componentId={componentId}
                        sessionId={sessionId}
                        timeRange={timeRange}
                        searchQuery={isSyncMode ? searchQuery : searchQuery}
                        logFilter={logFilter}
                        logLevels={logLevels}
                        useRegex={isSyncMode ? useRegex : useRegex}
                        timeSync={isTimeSync}
                        targetTimestamp={syncTimestamp}
                        onScrollSync={(ts) => setSyncTimestamp(ts)}
                        onRemove={() => removePanel(index)}
                        canRemove={panels.length > 1}
                        onComponentChange={(newId) => {
                            const newPanels = [...panels]
                            newPanels[index] = newId
                            setPanels(newPanels)
                        }}
                    />
                )}
            />

            {/* Footer */}
            <LogViewerPageFooter
                panelCount={panels.length}
                maxPanels={4}
                isLive={isConnected}
                tip={isConnected
                    ? "Live connection active - logs streaming"
                    : "Enter a Session ID to trace logs across components"}
            />
        </div>
    )
}

// IVA-specific Log Panel component
interface IVALogPanelProps {
    componentId: string
    sessionId?: string
    timeRange?: string
    searchQuery: string
    logFilter: 'all' | 'out' | 'err'
    logLevels: string[]
    useRegex: boolean
    timeSync?: boolean
    targetTimestamp?: string | null
    onScrollSync?: (timestamp: string) => void
    onRemove?: () => void
    canRemove?: boolean
    onComponentChange?: (componentId: string) => void
}

function IVALogPanel({
    componentId,
    sessionId,
    timeRange = '1h',
    searchQuery,
    logFilter,
    logLevels,
    useRegex,
    timeSync: _timeSync = false,
    targetTimestamp: _targetTimestamp = null,
    onScrollSync: _onScrollSync,
    onRemove,
    canRemove = false,
    onComponentChange,
}: IVALogPanelProps) {
    const {
        setComponentLogs,
        componentLogs,
        setComponentLoading
    } = useLogTracerStore()

    // Virtual list sizing
    const { ref: containerRef, width, height } = useContainerSize()

    // Initial fetch
    const { data, isLoading, refetch } = useQuery({
        queryKey: ['iva-logs', componentId, sessionId, timeRange],
        queryFn: async () => {
            setComponentLoading(componentId, true)
            const res = await logsApi.getLogs({
                component: componentId,
                sessionId: sessionId || undefined,
                timeRange,
                limit: 500,
            })
            // Initialize store with fetched logs
            setComponentLogs(componentId, res.logs as any)
            setComponentLoading(componentId, false)
            return res
        },
        enabled: !!componentId, // Fetch even without session ID (might be component logs only)
        staleTime: 60000,
    })

    // Get merged logs from store (initial + WS updates)
    const storeData = componentLogs[componentId]
    const displayLogs = storeData?.logs || data?.logs || []
    const isStoreLoading = storeData?.isLoading || isLoading

    const component = logsApi.COMPONENTS.find(c => c.id === componentId)

    return (
        <div className="flex flex-col h-full border rounded-md overflow-hidden bg-background">
            {/* Header */}
            <div className="flex items-center justify-between px-3 py-2 border-b bg-muted/30 h-10 shrink-0">
                <div className="flex items-center gap-2 overflow-hidden">
                    <select
                        value={componentId}
                        onChange={(e) => onComponentChange?.(e.target.value)}
                        className="h-7 px-2 text-xs border rounded bg-background focus:outline-none focus:ring-1 focus:ring-primary truncate"
                    >
                        {logsApi.COMPONENTS.map(c => (
                            <option key={c.id} value={c.id}>
                                {c.displayName}
                            </option>
                        ))}
                    </select>
                    <Badge variant="outline" className="text-[10px] px-1 shrink-0">
                        {component?.name || componentId}
                    </Badge>
                    <div className="text-xs text-muted-foreground ml-2">
                        {displayLogs.length} logs
                    </div>
                    {isStoreLoading && (
                        <Activity className="h-3 w-3 animate-pulse text-muted-foreground" />
                    )}
                </div>

                <div className="flex items-center gap-1">
                    <Button
                        variant="ghost"
                        size="sm"
                        className="h-6 px-2 text-[10px]"
                        onClick={() => refetch()}
                    >
                        Refresh
                    </Button>
                    {canRemove && (
                        <Button
                            variant="ghost"
                            size="sm"
                            className="h-6 w-6 p-0 hover:bg-destructive/10 hover:text-destructive"
                            onClick={onRemove}
                        >
                            ×
                        </Button>
                    )}
                </div>
            </div>

            {/* List */}
            <div ref={containerRef} className="flex-1 min-h-0 w-full relative">
                <VirtualizedLogRenderer
                    logs={displayLogs}
                    width={width}
                    height={height}
                    searchQuery={searchQuery}
                    useRegex={useRegex}
                    logFilter={logFilter}
                    logLevels={logLevels}
                    panelId={componentId}
                    panelIndex={0} // We need real index if we want time sync to distinguish source
                />
            </div>
        </div>
    )
}

// Wrapper to use hooks easier inside the render prop
function VirtualizedLogRenderer({
    logs, width, height, searchQuery, useRegex, logFilter, logLevels, panelId, panelIndex
}: any) {
    const listRef = useRef<any>(null)

    // Time Sync Hook
    const { handleLogClick } = useTimeSync({
        panelIndex,
        panelId,
        logs,
        listRef,
    })

    if (height === 0) return null

    return (
        <VirtualLogList
            ref={listRef}
            logs={logs}
            width={width}
            height={height}
            searchQuery={searchQuery}
            useRegex={useRegex}
            typeFilter={logFilter}
            levels={logLevels}
            onLogClick={handleLogClick}
        />
    )
}
