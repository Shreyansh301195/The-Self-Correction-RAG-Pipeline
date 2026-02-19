import React, { useState } from 'react';

function QueryInterface({ onSubmit, isLoading, error, result }) {
  const [query, setQuery] = useState('');

  const handleSubmit = (e) => {
    e.preventDefault();
    if (query.trim() && !isLoading) {
      onSubmit(query.trim());
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
      handleSubmit(e);
    }
  };

  return (
    <div className="query-interface">
      <form onSubmit={handleSubmit} className="query-form">
        <div className="query-input-wrapper">
          <textarea
            className="query-textarea"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask a technical question about telecom devices...&#10;e.g. How do I reset a Cisco ASR 9000 router?"
            rows={4}
            disabled={isLoading}
          />
          <div className="query-input-footer">
            <span className="query-hint">Ctrl+Enter to submit</span>
            <button
              type="submit"
              className={`submit-btn ${isLoading ? 'loading' : ''}`}
              disabled={isLoading || !query.trim()}
            >
              {isLoading ? (
                <>
                  <span className="spinner" />
                  Processing...
                </>
              ) : (
                <>🔍 Run RAG Pipeline</>
              )}
            </button>
          </div>
        </div>
      </form>

      {/* Error */}
      {error && (
        <div className="alert alert-error">
          <span>⚠️</span>
          <div>
            <strong>Error</strong>
            <p>{error}</p>
          </div>
        </div>
      )}

      {/* Loading State */}
      {isLoading && (
        <div className="pipeline-progress">
          <h3>Running Corrective RAG Pipeline...</h3>
          <div className="progress-steps">
            {['Retrieving Documents', 'Grading Relevance', 'Generating Answer', 'Checking Groundedness', 'Guardrail Check'].map((step, i) => (
              <div key={step} className="progress-step">
                <div className="progress-dot progress-dot-active" style={{ animationDelay: `${i * 0.3}s` }} />
                <span>{step}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Result */}
      {result && !isLoading && (
        <div className="result-section">
          {/* Query Used */}
          <div className="result-query">
            <span className="label">Original Query:</span>
            <span>{result.query}</span>
            {result.metadata?.rewritten_query && result.metadata.rewritten_query !== result.query && (
              <div className="rewrite-note">
                <span className="label rewrite-label">🔄 Rewritten to:</span>
                <span className="rewrite-text">{result.metadata.rewritten_query}</span>
              </div>
            )}
          </div>

          {/* Answer */}
          <div className="answer-card">
            <div className="answer-header">
              <h3>💬 Answer</h3>
              <span className={`processing-time ${result.processing_time_ms > 5000 ? 'slow' : ''}`}>
                ⏱ {(result.processing_time_ms / 1000).toFixed(2)}s
              </span>
            </div>
            <div className="answer-content">
              {result.final_answer.split('\n').map((line, i) => (
                <p key={i}>{line}</p>
              ))}
            </div>
          </div>

          {/* Sources */}
          {result.metadata?.sources_used?.length > 0 && (
            <div className="sources-section">
              <h4>📚 Sources Used</h4>
              <div className="sources-grid">
                {result.metadata.sources_used.map((src, i) => (
                  <div key={i} className="source-card">
                    <div className="source-header">
                      <span className="source-device">{src.device}</span>
                      <span className="source-category">{src.category}</span>
                    </div>
                    <p className="source-snippet">{src.snippet}</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Error from pipeline */}
          {result.metadata?.error && (
            <div className="alert alert-warning">
              <span>⚠️</span>
              <p><strong>Pipeline warning:</strong> {result.metadata.error}</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default QueryInterface;
