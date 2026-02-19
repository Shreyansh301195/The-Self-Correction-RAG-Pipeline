import React, { useState } from 'react';

const NODE_COLORS = {
  retrieve: '#3b82f6',
  grade_relevance: '#8b5cf6',
  rewrite_query: '#f59e0b',
  generate: '#10b981',
  check_groundedness: '#6366f1',
  guardrail: '#ef4444',
  finalize: '#22c55e',
};

const NODE_ICONS = {
  retrieve: '🔍',
  grade_relevance: '⚖️',
  rewrite_query: '✏️',
  generate: '💬',
  check_groundedness: '🔬',
  guardrail: '🛡️',
  finalize: '✅',
};

const DECISION_COLORS = {
  relevant: '#10b981',
  irrelevant: '#ef4444',
  grounded: '#10b981',
  hallucinated: '#ef4444',
  guardrail_pass: '#10b981',
  guardrail_fail: '#ef4444',
  rewritten: '#f59e0b',
  retrieved: '#3b82f6',
  generated: '#6366f1',
  completed: '#22c55e',
  error: '#ef4444',
};

function TraceStep({ step, index, isExpanded, onToggle }) {
  const color = NODE_COLORS[step.node] || '#64748b';
  const icon = NODE_ICONS[step.node] || '⚙️';
  const decisionColor = DECISION_COLORS[step.decision] || '#64748b';
  const timestamp = step.timestamp ? new Date(step.timestamp * 1000).toLocaleTimeString() : '';

  return (
    <div className="trace-step" style={{ borderLeftColor: color }}>
      <div className="trace-step-header" onClick={onToggle}>
        <div className="trace-step-left">
          <span className="trace-step-index">{index + 1}</span>
          <span className="trace-node-icon">{icon}</span>
          <span className="trace-node-name" style={{ color }}>{step.node}</span>
        </div>
        <div className="trace-step-right">
          <span
            className="trace-decision-badge"
            style={{ backgroundColor: decisionColor + '20', color: decisionColor, borderColor: decisionColor }}
          >
            {step.decision}
          </span>
          {timestamp && <span className="trace-timestamp">{timestamp}</span>}
          <span className="trace-expand-icon">{isExpanded ? '▲' : '▼'}</span>
        </div>
      </div>

      {isExpanded && step.details && Object.keys(step.details).length > 0 && (
        <div className="trace-step-details">
          {Object.entries(step.details).map(([key, value]) => (
            <div key={key} className="trace-detail-row">
              <span className="trace-detail-key">{key}:</span>
              <span className="trace-detail-value">
                {Array.isArray(value)
                  ? value.join(', ') || 'none'
                  : typeof value === 'boolean'
                  ? value ? '✅ Yes' : '❌ No'
                  : typeof value === 'number'
                  ? typeof key.includes('score') ? value.toFixed(3) : value
                  : String(value)}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function TraceViewer({ trace, sessionId, processingTime }) {
  const [expandedSteps, setExpandedSteps] = useState(new Set([0, trace.length - 1]));

  const toggleStep = (index) => {
    setExpandedSteps(prev => {
      const next = new Set(prev);
      if (next.has(index)) next.delete(index);
      else next.add(index);
      return next;
    });
  };

  const expandAll = () => setExpandedSteps(new Set(trace.map((_, i) => i)));
  const collapseAll = () => setExpandedSteps(new Set());

  if (!trace || trace.length === 0) {
    return (
      <div className="trace-empty">
        <div className="trace-empty-icon">📊</div>
        <h3>No trace data yet</h3>
        <p>Submit a query to see the decision trace</p>
      </div>
    );
  }

  // Derive pipeline summary
  const hasRewrite = trace.some(t => t.node === 'rewrite_query');
  const relevanceStep = trace.find(t => t.node === 'grade_relevance');
  const groundednessStep = trace.find(t => t.node === 'check_groundedness');
  const guardrailStep = trace.find(t => t.node === 'guardrail');

  return (
    <div className="trace-viewer">
      {/* Summary */}
      <div className="trace-summary">
        <h3>Pipeline Execution Summary</h3>
        <div className="trace-summary-grid">
          <div className="trace-summary-item">
            <span className="summary-label">Steps</span>
            <span className="summary-value">{trace.length}</span>
          </div>
          <div className="trace-summary-item">
            <span className="summary-label">Query Rewritten</span>
            <span className={`summary-value ${hasRewrite ? 'text-warning' : 'text-success'}`}>
              {hasRewrite ? `Yes` : 'No'}
            </span>
          </div>
          <div className="trace-summary-item">
            <span className="summary-label">Relevance</span>
            <span className={`summary-value ${relevanceStep?.decision === 'relevant' ? 'text-success' : 'text-error'}`}>
              {relevanceStep?.details?.relevance_score?.toFixed(2) || 'N/A'}
            </span>
          </div>
          <div className="trace-summary-item">
            <span className="summary-label">Groundedness</span>
            <span className={`summary-value ${groundednessStep?.details?.groundedness_score >= 0.6 ? 'text-success' : 'text-warning'}`}>
              {groundednessStep?.details?.groundedness_score?.toFixed(2) || 'N/A'}
            </span>
          </div>
          <div className="trace-summary-item">
            <span className="summary-label">Guardrail</span>
            <span className={`summary-value ${guardrailStep?.decision === 'guardrail_pass' ? 'text-success' : 'text-error'}`}>
              {guardrailStep?.decision === 'guardrail_pass' ? 'PASSED' : guardrailStep ? 'FAILED' : 'N/A'}
            </span>
          </div>
          {processingTime && (
            <div className="trace-summary-item">
              <span className="summary-label">Total Time</span>
              <span className="summary-value">{(processingTime / 1000).toFixed(2)}s</span>
            </div>
          )}
        </div>
        {sessionId && (
          <div className="session-id">
            Session: <code>{sessionId}</code>
          </div>
        )}
      </div>

      {/* Controls */}
      <div className="trace-controls">
        <h4>Decision Log ({trace.length} steps)</h4>
        <div>
          <button className="btn-small" onClick={expandAll}>Expand All</button>
          <button className="btn-small" onClick={collapseAll}>Collapse All</button>
        </div>
      </div>

      {/* Steps */}
      <div className="trace-steps">
        {trace.map((step, i) => (
          <TraceStep
            key={i}
            step={step}
            index={i}
            isExpanded={expandedSteps.has(i)}
            onToggle={() => toggleStep(i)}
          />
        ))}
      </div>
    </div>
  );
}

export default TraceViewer;
