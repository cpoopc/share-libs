import { Routes, Route, Navigate } from 'react-router-dom'
import { MfeLayout } from '@cptools/router'
import { LogTracerPage } from './pages/LogTracerPage'
import { TurnAnalysisPage } from './pages/TurnAnalysisPage'

function App() {
    return (
        <Routes>
            <Route element={<MfeLayout />}>
                <Route index element={<LogTracerPage />} />
                <Route path="analysis/:sessionId" element={<TurnAnalysisPage />} />
                <Route path="*" element={<Navigate to="." replace />} />
            </Route>
        </Routes>
    )
}

export default App
