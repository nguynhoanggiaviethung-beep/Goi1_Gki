import { useEffect, useState } from 'react'
import './App.css'

const apiBase = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

function App() {
  const [status, setStatus] = useState('Đang kết nối...')

  useEffect(() => {
    fetch(apiBase + '/api/health')
      .then((response) => {
        if (!response.ok) throw new Error('API error')
        return response.json()
      })
      .then((data: { status: string }) => setStatus(data.status))
      .catch(() => setStatus('Chưa kết nối được backend'))
  }, [])

  return (
    <>
      <h1>Goi1_Gki</h1>
      <p>Frontend React + Vite đã sẵn sàng.</p>
      <p>Backend: <strong>{status}</strong></p>
      <a href={apiBase + '/docs'} target="_blank" rel="noreferrer">Mở API docs</a>
    </>
  )
}

export default App
