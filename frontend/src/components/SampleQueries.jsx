import React, { useEffect } from 'react';
import { useSampleQueries } from '../hooks/useRAGQuery';

const DEVICE_COLORS = {
  'Cisco ASR 9000': '#049fd9',
  'Nokia 7750 SR': '#005AFF',
  'Juniper MX Series': '#84C225',
  'N/A (tests irrelevance)': '#6b7280',
  'General Telecom': '#8b5cf6',
};

function SampleQueries({ onSelect }) {
  const { samples, loading, fetchSamples } = useSampleQueries();

  useEffect(() => {
    fetchSamples();
  }, [fetchSamples]);

  if (loading) {
    return <div className="sample-queries-loading">Loading samples...</div>;
  }

  return (
    <div className="sample-queries">
      <h3>💡 Sample Queries</h3>
      <p className="sample-hint">Click to run in pipeline</p>
      <div className="sample-list">
        {(samples || []).map((sample) => {
          const color = DEVICE_COLORS[sample.device] || '#6b7280';
          return (
            <button
              key={sample.id}
              className="sample-item"
              onClick={() => onSelect(sample.query)}
              title={`Device: ${sample.device}`}
            >
              <div className="sample-item-header">
                <span
                  className="sample-device-dot"
                  style={{ backgroundColor: color }}
                />
                <span className="sample-device-name" style={{ color }}>
                  {sample.device}
                </span>
              </div>
              <p className="sample-query-text">{sample.query}</p>
              {sample.expected_path && (
                <p className="sample-path">→ {sample.expected_path}</p>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}

export default SampleQueries;
