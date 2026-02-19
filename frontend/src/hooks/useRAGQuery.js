import { useState, useCallback } from 'react';

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export function useRAGQuery() {
  const [result, setResult] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);

  const submitQuery = useCallback(async (query) => {
    if (!query || !query.trim()) return;

    setIsLoading(true);
    setError(null);
    setResult(null);

    try {
      const response = await fetch(`${API_BASE}/query`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: query.trim() }),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `HTTP ${response.status}: ${response.statusText}`);
      }

      const data = await response.json();
      setResult(data);
    } catch (err) {
      console.error('Query failed:', err);
      if (err.name === 'TypeError' && err.message.includes('fetch')) {
        setError('Cannot connect to backend. Make sure the FastAPI server is running on port 8000.');
      } else {
        setError(err.message || 'An unexpected error occurred');
      }
    } finally {
      setIsLoading(false);
    }
  }, []);

  return { result, isLoading, error, submitQuery };
}

export function useSampleQueries() {
  const [samples, setSamples] = useState(null);
  const [loading, setLoading] = useState(false);

  const fetchSamples = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/sample-queries`);
      const data = await res.json();
      setSamples(data.queries);
    } catch (e) {
      console.error('Failed to fetch samples:', e);
      // Use fallback samples
      setSamples([
        { id: 1, query: 'How do I reset a Cisco ASR 9000 to factory defaults?', device: 'Cisco ASR 9000' },
        { id: 2, query: 'BGP troubleshooting steps for Nokia 7750 SR', device: 'Nokia 7750 SR' },
        { id: 3, query: 'Configure MPLS on Juniper MX Series', device: 'Juniper MX Series' },
        { id: 4, query: 'QoS configuration for voice traffic on ASR 9000', device: 'Cisco ASR 9000' },
        { id: 5, query: 'pizza recipe', device: 'N/A (tests irrelevance)' },
      ]);
    } finally {
      setLoading(false);
    }
  }, []);

  return { samples, loading, fetchSamples };
}
