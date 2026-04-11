import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
    Activity, Clock, MessageSquare, AlertTriangle,
    ChevronRight, ChevronDown, ArrowLeft, Terminal
} from 'lucide-react'
import axios from 'axios'
import { Button, Card, Badge, cn } from '@cptools/ui'

interface TurnAnalysisResponse {
    session_id: string
    conversation_id?: string
    total_turns: number
    total_duration_ms?: number
    summary: {
        avg_turn_duration_ms?: number
        avg_ttft_ms?: number
        total_tools_called: number
        error_count: number
    }
    turns: Turn[]
}

interface Turn {
    turn_number: number
    start_time: string
    end_time?: string
    duration_ms?: number
    user_input?: string
    bot_response?: string
    state: string
    ttft_ms?: number
    tools_called: string[]
    errors: string[]
    events: TurnEvent[]
}

interface TurnEvent {
    timestamp: string
    type: string
    component: string
    message: string
    duration_ms?: number
    metadata?: any
}

export function TurnAnalysisPage() {
    const { sessionId } = useParams<{ sessionId: string }>()
    const navigate = useNavigate()
    const [expandedTurns, setExpandedTurns] = useState<Set<number>>(new Set())

    const { data: analysis, isLoading, error } = useQuery({
        queryKey: ['turn-analysis', sessionId],
        queryFn: async () => {
            const res = await axios.get<TurnAnalysisResponse>(`/api/turn-analysis/sessions/${sessionId}`)
            return res.data
        },
        enabled: !!sessionId,
    })

    const toggleTurn = (turnNum: number) => {
        const newSet = new Set(expandedTurns)
        if (newSet.has(turnNum)) {
            newSet.delete(turnNum)
        } else {
            newSet.add(turnNum)
        }
        setExpandedTurns(newSet)
    }

    const expandAll = () => {
        if (analysis) {
            setExpandedTurns(new Set(analysis.turns.map(t => t.turn_number)))
        }
    }

    const collapseAll = () => {
        setExpandedTurns(new Set())
    }

    if (isLoading) {
        return (
            <div className="flex h-full items-center justify-center">
                <Activity className="h-8 w-8 animate-spin text-muted-foreground" />
                <span className="ml-2 text-muted-foreground">Analyzing session turns...</span>
            </div>
        )
    }

    if (error || !analysis) {
        return (
            <div className="flex h-full flex-col items-center justify-center gap-4">
                <div className="text-destructive font-medium">Failed to load turn analysis</div>
                <div className="text-sm text-muted-foreground">{String(error)}</div>
                <Button onClick={() => navigate('/')}>Back to Log Tracer</Button>
            </div>
        )
    }

    return (
        <div className="flex flex-col h-full bg-muted/10 overflow-hidden">
            {/* Header */}
            <div className="flex items-center justify-between px-6 py-4 bg-background border-b shrink-0">
                <div className="flex items-center gap-4">
                    <Button variant="ghost" size="icon" onClick={() => navigate(`/?sessionId=${sessionId}`)}>
                        <ArrowLeft className="h-4 w-4" />
                    </Button>
                    <div>
                        <h1 className="text-lg font-semibold flex items-center gap-2">
                            Turn Analysis
                            <Badge variant="outline" className="font-mono text-xs font-normal">
                                {sessionId}
                            </Badge>
                        </h1>
                        <div className="text-sm text-muted-foreground flex items-center gap-4 mt-1">
                            <span className="flex items-center gap-1">
                                <MessageSquare className="h-3 w-3" /> {analysis.total_turns} turns
                            </span>
                            {analysis.summary.avg_ttft_ms && (
                                <span className="flex items-center gap-1">
                                    <Activity className="h-3 w-3" /> Avg TTFT: {Math.round(analysis.summary.avg_ttft_ms)}ms
                                </span>
                            )}
                            <span className="flex items-center gap-1">
                                <Clock className="h-3 w-3" /> Total Duration: {((analysis.summary.avg_turn_duration_ms || 0) * analysis.total_turns / 1000).toFixed(1)}s
                            </span>
                            {analysis.summary.error_count > 0 && (
                                <span className="flex items-center gap-1 text-destructive">
                                    <AlertTriangle className="h-3 w-3" /> {analysis.summary.error_count} errors
                                </span>
                            )}
                        </div>
                    </div>
                </div>

                <div className="flex items-center gap-2">
                    <Button variant="outline" size="sm" onClick={expandAll}>Expand All</Button>
                    <Button variant="outline" size="sm" onClick={collapseAll}>Collapse All</Button>
                </div>
            </div>

            {/* Content */}
            <div className="flex-1 overflow-auto p-6">
                <div className="max-w-4xl mx-auto space-y-4">
                    {analysis.turns.map((turn) => (
                        <TurnCard
                            key={turn.turn_number}
                            turn={turn}
                            isExpanded={expandedTurns.has(turn.turn_number)}
                            onToggle={() => toggleTurn(turn.turn_number)}
                        />
                    ))}
                </div>
            </div>
        </div>
    )
}

function TurnCard({ turn, isExpanded, onToggle }: { turn: Turn, isExpanded: boolean, onToggle: () => void }) {
    const hasError = turn.errors.length > 0
    const duration = turn.duration_ms ? (turn.duration_ms / 1000).toFixed(1) + 's' : '-'

    return (
        <Card className={cn("overflow-hidden transition-all", hasError && "border-destructive/50 bg-destructive/5")}>
            <div
                className="flex items-center gap-4 p-4 cursor-pointer hover:bg-muted/50 transition-colors"
                onClick={onToggle}
            >
                <div className={cn(
                    "h-8 w-8 rounded-full flex items-center justify-center font-bold text-sm shrink-0",
                    hasError ? "bg-destructive/20 text-destructive" : "bg-primary/20 text-primary"
                )}>
                    {turn.turn_number}
                </div>

                <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between mb-1">
                        <div className="font-medium truncate pr-4">
                            {turn.user_input || <span className="text-muted-foreground italic">No user input</span>}
                        </div>
                        <div className="text-xs text-muted-foreground font-mono shrink-0">
                            {new Date(turn.start_time).toLocaleTimeString()} • {duration}
                        </div>
                    </div>

                    <div className="flex items-center gap-4 text-sm text-muted-foreground">
                        <div className="flex items-center gap-1.5 truncate max-w-[60%]">
                            <Terminal className="h-3 w-3" />
                            {turn.bot_response || <span className="italic">Processing...</span>}
                        </div>

                        <div className="flex items-center gap-2 shrink-0">
                            {turn.ttft_ms && (
                                <Badge variant="secondary" className="text-[10px] h-5">
                                    TTFT: {turn.ttft_ms}ms
                                </Badge>
                            )}
                            {turn.tools_called.length > 0 && (
                                <Badge variant="outline" className="text-[10px] h-5 gap-1">
                                    <Activity className="h-3 w-3" /> {turn.tools_called.length} tools
                                </Badge>
                            )}
                        </div>
                    </div>
                </div>

                <div className="shrink-0">
                    {isExpanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                </div>
            </div>

            {isExpanded && (
                <div className="border-t bg-muted/20 p-4 space-y-4 text-sm animate-in slide-in-from-top-2 duration-200">
                    {/* Events Timeline */}
                    <div className="relative pl-4 border-l-2 custom-timeline">
                        {turn.events.map((event, i) => (
                            <div key={i} className="mb-4 last:mb-0 relative">
                                <div className="absolute -left-[21px] top-1 h-3 w-3 rounded-full border bg-background" />
                                <div className="flex flex-col gap-1">
                                    <div className="flex items-center gap-2">
                                        <Badge variant="outline" className="text-[10px] font-mono">
                                            {event.component}
                                        </Badge>
                                        <span className="text-xs text-muted-foreground font-mono">
                                            {new Date(event.timestamp).toLocaleTimeString([], { hour12: false, fractionalSecondDigits: 3 } as any)}
                                        </span>
                                        <span className={cn(
                                            "text-xs font-semibold uppercase",
                                            event.type === 'error' && "text-destructive",
                                            event.type === 'tool_call' && "text-blue-500",
                                            event.type === 'ttft' && "text-green-600"
                                        )}>
                                            {event.type}
                                        </span>
                                    </div>
                                    <div className="text-muted-foreground break-words font-mono text-xs pl-2 border-l-2 border-muted">
                                        {event.message}
                                    </div>
                                </div>
                            </div>
                        ))}
                    </div>

                    {/* Tool Calls Detail */}
                    {turn.tools_called.length > 0 && (
                        <div className="mt-4 pt-4 border-t">
                            <h4 className="font-medium text-xs uppercase text-muted-foreground mb-2">Tools Called</h4>
                            <div className="flex flex-wrap gap-2">
                                {turn.tools_called.map((tool, i) => (
                                    <Badge key={i} variant="secondary">{tool}</Badge>
                                ))}
                            </div>
                        </div>
                    )}

                    {/* Errors Detail */}
                    {turn.errors.length > 0 && (
                        <div className="mt-4 pt-4 border-t">
                            <h4 className="font-medium text-xs uppercase text-destructive mb-2">Errors</h4>
                            {turn.errors.map((err, i) => (
                                <div key={i} className="text-destructive text-xs font-mono bg-destructive/10 p-2 rounded">
                                    {err}
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            )}
        </Card>
    )
}
