import React from 'react';

function GaugeBar({ value, max = 1, label, color }) {
  const pct = Math.min(100, Math.round((value / max) * 100));
  return (
    <div className="gauge-bar">
      <div className="gauge-header">
        <span className="gauge-label">{label}</span>
        <span className="gauge-value" style={{ color }}>{(value * 100).toFixed(0)}%</span>
      </div>
      <div className="gauge-track">
        <div
          className="gauge-fill"
          style={{ width: `${pct}%`, backgroundColor: color }}
        />
      </div>
    </div>
  );
}

function ScoreCard({ result }) {
  if (!result) return null;

  const { scores, metadata } = result;

  const relevanceColor = scores.relevance >= 0.7 ? '#10b981' : scores.relevance >= 0.5 ? '#f59e0b' : '#ef4444';
  const groundednessColor = scores.groundedness >= 0.7 ? '#10b981' : scores.groundedness >= 0.5 ? '#f59e0b' : '#ef4444';

  const overallStatus = scores.guardrail_passed && scores.relevance >= 0.5 && scores.groundedness >= 0.6
    ? { label: 'HIGH QUALITY', color: '#10b981', icon: '✅' }
    : scores.guardrail_passed && scores.relevance >= 0.3
    ? { label: 'ACCEPTABLE', color: '#f59e0b', icon: '⚠️' }
    : { label: 'LOW QUALITY', color: '#ef4444', icon: '❌' };

  return (
    <div className="score-card">
      <div className="score-card-header">
        <h3>📊 Evaluation Scores</h3>
        <span
          className="overall-status"
          style={{ color: overallStatus.color, borderColor: overallStatus.color }}
        >
          {overallStatus.icon} {overallStatus.label}
        </span>
      </div>

      <div className="score-metrics">
        <GaugeBar
          value={scores.relevance}
          label="Context Relevance"
          color={relevanceColor}
        />
        <GaugeBar
          value={scores.groundedness}
          label="Groundedness"
          color={groundednessColor}
        />
      </div>

      <div className="score-flags">
        <div className={`flag ${scores.guardrail_passed ? 'flag-pass' : 'flag-fail'}`}>
          {scores.guardrail_passed ? '🛡️ Guardrail: PASS' : '🛡️ Guardrail: FAIL'}
        </div>
        {metadata?.rewrite_count > 0 && (
          <div className="flag flag-warning">
            ✏️ Rewritten: {metadata.rewrite_count}x
          </div>
        )}
      </div>

      {metadata?.mentioned_devices?.length > 0 && (
        <div className="devices-section">
          <span className="devices-label">Devices in context:</span>
          <div className="devices-list">
            {metadata.mentioned_devices.map(d => (
              <span key={d} className="device-chip">{d}</span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export default ScoreCard;
