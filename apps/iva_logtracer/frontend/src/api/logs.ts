import axios from 'axios'
import type { LogEntry } from '@cptools/ui'

const api = axios.create({
    baseURL: '/api/logtracer',
})

export interface Component {
    id: string
    name: string
    displayName: string
    indexPattern: string
}

export interface SessionInfo {
    sessionId: string
    conversationId?: string
    srsSessionId?: string
    components: string[]
}

export interface LogQueryParams {
    component: string
    sessionId?: string
    conversationId?: string
    timeRange?: string
    startTime?: string
    endTime?: string
    query?: string
    levels?: string[]
    limit?: number
}

// Available IVA components
export const COMPONENTS: Component[] = [
    { id: 'assistant_runtime', name: 'assistant_runtime', displayName: 'Assistant Runtime', indexPattern: '*:*-logs-air_assistant_runtime-*' },
    { id: 'agent_service', name: 'agent_service', displayName: 'Agent Service', indexPattern: '*:*-logs-air_agent_service-*' },
    { id: 'nca', name: 'nca', displayName: 'NCA', indexPattern: '*:*-logs-nca-*' },
    { id: 'aig', name: 'aig', displayName: 'AIG', indexPattern: '*:*-logs-aig-*' },
    { id: 'gmg', name: 'gmg', displayName: 'GMG', indexPattern: '*:*-logs-gmg-*' },
    { id: 'cprc_srs', name: 'cprc_srs', displayName: 'CPRC SRS', indexPattern: '*:*-ai-cprc*' },
    { id: 'cprc_sgs', name: 'cprc_sgs', displayName: 'CPRC SGS', indexPattern: '*:*-ai-cprc*' },
]

export async function getComponents(): Promise<Component[]> {
    return COMPONENTS
}

export async function getLogs(params: LogQueryParams): Promise<{ logs: LogEntry[], total: number }> {
    try {
        const response = await api.get('/logs', { params })
        return response.data
    } catch (error) {
        console.error('Failed to fetch logs:', error)
        // Return mock data for development
        return {
            logs: generateMockLogs(params.component, params.limit || 100),
            total: 100,
        }
    }
}

export async function getSession(sessionId: string): Promise<SessionInfo | null> {
    try {
        const response = await api.get(`/sessions/${sessionId}`)
        return response.data
    } catch (error) {
        console.error('Failed to fetch session:', error)
        return null
    }
}

// Mock data for development
function generateMockLogs(component: string, count: number): LogEntry[] {
    const messages = [
        'Processing request...',
        'Connected to service',
        'Executing turn handler',
        'Received response from agent',
        'Session initialized',
        'Turn completed successfully',
        'Error: Connection timeout',
        'Warning: Rate limit approaching',
        'Debug: State transition',
        'Info: Health check passed',
    ]

    return Array.from({ length: count }, (_, i) => ({
        timestamp: new Date(Date.now() - (count - i) * 1000).toISOString(),
        type: i % 10 === 6 ? 'err' : 'out',
        message: `[${component}] ${messages[i % messages.length]}`,
        source: component,
    }))
}
