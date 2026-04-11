import ReactDOM from 'react-dom/client'
import { MfeContainer } from '@cptools/router'
import App from './App'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
    <MfeContainer appName="iva-logtracer">
        <App />
    </MfeContainer>
)
