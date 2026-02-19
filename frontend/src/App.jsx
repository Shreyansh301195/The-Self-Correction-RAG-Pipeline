import React, { useState } from 'react';
import QueryInterface from './components/QueryInterface';
import TraceViewer from './components/TraceViewer';
import SampleQueries from './components/SampleQueries';
import ScoreCard from './components/ScoreCard';
import ArchitectureDiagram from './components/ArchitectureDiagram';
import { useRAGQuery } from './hooks/useRAGQuery';
import './App.css';

function App() {
  const [activeTab, setActiveTab] = useState('query');
  const { result, isLoading, error, submitQuery } = useRAGQuery();

  const tabs = [
    { id: 'query', label: '🔍 Query', icon: '🔍' },
    { id: 'trace', label: '📊 Decision Trace', icon: '📊' },
    { id: 'architecture', label: '🏗️ Architecture', icon: '🏗️' },
  ];

  return (
    <div className="app">
      {/* Header */}
      <header className="app-header">
        <div className="header-content">
          <div className="logo">
            <span className="logo-icon">🌐</span>
            <div>
              <h1>Corrective RAG</h1>
              <p>Telecom OSS/BSS Support — Self-Correcting Pipeline</p>
            </div>
          </div>
          <div className="header-badges">
            <span className="badge badge-green">LangGraph</span>
            <span className="badge badge-blue">LangSmith</span>
            <span className="badge badge-purple">ChromaDB</span>
            <span className="badge badge-orange">FastAPI</span>
          </div>
        </div>
      </header>

      {/* Pipeline Flow Banner */}
      <div className="pipeline-banner">
        {['Retrieve', 'Grade', 'Rewrite?', 'Generate', 'Groundedness', 'Guardrail', 'Answer'].map((step, i) => (
          <React.Fragment key={step}>
            <div className="pipeline-step">{step}</div>
            {i < 6 && <span className="pipeline-arrow">→</span>}
          </React.Fragment>
        ))}
      </div>

      {/* Main Content */}
      <div className="main-container">
        {/* Left Panel */}
        <div className="left-panel">
          <SampleQueries onSelect={submitQuery} />
          {result && <ScoreCard result={result} />}
        </div>

        {/* Right Panel */}
        <div className="right-panel">
          {/* Tabs */}
          <div className="tabs">
            {tabs.map(tab => (
              <button
                key={tab.id}
                className={`tab ${activeTab === tab.id ? 'tab-active' : ''}`}
                onClick={() => setActiveTab(tab.id)}
              >
                {tab.label}
                {tab.id === 'trace' && result?.decision_trace?.length > 0 && (
                  <span className="tab-badge">{result.decision_trace.length}</span>
                )}
              </button>
            ))}
          </div>

          {/* Tab Content */}
          <div className="tab-content">
            {activeTab === 'query' && (
              <QueryInterface
                onSubmit={submitQuery}
                isLoading={isLoading}
                error={error}
                result={result}
              />
            )}
            {activeTab === 'trace' && (
              <TraceViewer
                trace={result?.decision_trace || []}
                sessionId={result?.session_id}
                processingTime={result?.processing_time_ms}
              />
            )}
            {activeTab === 'architecture' && <ArchitectureDiagram />}
          </div>
        </div>
      </div>
    </div>
  );
}

export default App;
