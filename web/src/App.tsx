import React from 'react'

export default function App() {
  return (
    <div style={{ fontFamily: 'system-ui, sans-serif', padding: 24 }}>
      <h1>PersonalCodex</h1>
      <p>
        Web UI for scripture notes and journals. This is a minimal scaffold.
      </p>
      <ul>
        <li>Search, tags, cross-references to scriptures</li>
        <li>OCR for scanned notes (PDF/images)</li>
        <li>Local-first, containerized runtime</li>
      </ul>
      <p>
        API health: <a href="http://localhost:8000/healthz">/healthz</a> — Docs: <a href="http://localhost:8000/docs">/docs</a>
      </p>
    </div>
  )
}

