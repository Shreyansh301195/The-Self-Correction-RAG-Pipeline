import React, { useState } from 'react';

const nodes = [
  { id: 'user', x: 50, y: 180, w: 100, h: 44, label: '👤 User Query', color: '#6366f1', textColor: '#fff' },
  { id: 'retrieve', x: 210, y: 180, w: 110, h: 44, label: '🔍 Retrieve', color: '#3b82f6', textColor: '#fff' },
  { id: 'grade', x: 380, y: 180, w: 130, h: 44, label: '⚖️ Grade Relevance', color: '#8b5cf6', textColor: '#fff' },
  { id: 'rewrite', x: 380, y: 290, w: 130, h: 44, label: '✏️ Rewrite Query', color: '#f59e0b', textColor: '#fff' },
  { id: 'generate', x: 570, y: 180, w: 110, h: 44, label: '💬 Generate', color: '#10b981', textColor: '#fff' },
  { id: 'groundedness', x: 570, y: 290, w: 130, h: 44, label: '🔬 Groundedness', color: '#6366f1', textColor: '#fff' },
  { id: 'guardrail', x: 760, y: 180, w: 110, h: 44, label: '🛡️ Guardrail', color: '#ef4444', textColor: '#fff' },
  { id: 'answer', x: 930, y: 180, w: 100, h: 44, label: '✅ Final Answer', color: '#22c55e', textColor: '#fff' },
  // Infrastructure
  { id: 'chromadb', x: 210, y: 330, w: 110, h: 40, label: '🗄️ ChromaDB', color: '#1e293b', textColor: '#94a3b8', dashed: true },
  { id: 'langsmith', x: 760, y: 330, w: 120, h: 40, label: '📡 LangSmith', color: '#1e293b', textColor: '#94a3b8', dashed: true },
  { id: 'llm', x: 570, y: 400, w: 130, h: 40, label: '🤖 LLM (Open Source)', color: '#1e293b', textColor: '#94a3b8', dashed: true },
];

const edges = [
  { from: 'user', to: 'retrieve', label: 'query' },
  { from: 'retrieve', to: 'grade', label: 'docs' },
  { from: 'grade', to: 'rewrite', label: 'irrelevant', dashed: true, color: '#ef4444' },
  { from: 'rewrite', to: 'retrieve', label: 'retry', dashed: true, color: '#f59e0b' },
  { from: 'grade', to: 'generate', label: 'relevant' },
  { from: 'generate', to: 'groundedness', label: 'answer' },
  { from: 'groundedness', to: 'guardrail', label: 'grounded' },
  { from: 'groundedness', to: 'answer', label: 'hallucinated→warn', dashed: true, color: '#ef4444' },
  { from: 'guardrail', to: 'answer', label: 'pass' },
];

function getNodeCenter(id) {
  const n = nodes.find(n => n.id === id);
  if (!n) return { x: 0, y: 0 };
  return { x: n.x + n.w / 2, y: n.y + n.h / 2 };
}

export default function ArchitectureDiagram() {
  const [hovered, setHovered] = useState(null);

  return (
    <div className="architecture-view">
      <h3>System Architecture — Corrective RAG Pipeline</h3>
      <p className="arch-subtitle">
        LangGraph state machine with conditional routing, LLM-as-judge evaluation, and guardrails.
      </p>

      <div className="arch-diagram-wrapper">
        <svg viewBox="0 0 1100 480" className="arch-svg">
          <defs>
            <marker id="arrow" markerWidth="8" markerHeight="8" refX="8" refY="4" orient="auto">
              <path d="M0,0 L8,4 L0,8 Z" fill="#475569" />
            </marker>
            <marker id="arrow-red" markerWidth="8" markerHeight="8" refX="8" refY="4" orient="auto">
              <path d="M0,0 L8,4 L0,8 Z" fill="#ef4444" />
            </marker>
            <marker id="arrow-yellow" markerWidth="8" markerHeight="8" refX="8" refY="4" orient="auto">
              <path d="M0,0 L8,4 L0,8 Z" fill="#f59e0b" />
            </marker>
          </defs>

          {/* Edges */}
          {edges.map((edge, i) => {
            const from = getNodeCenter(edge.from);
            const to = getNodeCenter(edge.to);
            const color = edge.color || '#475569';
            const markerId = edge.color === '#ef4444' ? 'arrow-red' : edge.color === '#f59e0b' ? 'arrow-yellow' : 'arrow';
            const midX = (from.x + to.x) / 2;
            const midY = (from.y + to.y) / 2;

            return (
              <g key={i}>
                <line
                  x1={from.x} y1={from.y}
                  x2={to.x} y2={to.y}
                  stroke={color}
                  strokeWidth={edge.dashed ? 1.5 : 2}
                  strokeDasharray={edge.dashed ? '5,4' : 'none'}
                  markerEnd={`url(#${markerId})`}
                  opacity={0.8}
                />
                {edge.label && (
                  <text x={midX} y={midY - 6} textAnchor="middle" fontSize="10" fill={color} opacity={0.9}>
                    {edge.label}
                  </text>
                )}
              </g>
            );
          })}

          {/* Nodes */}
          {nodes.map(node => (
            <g
              key={node.id}
              onMouseEnter={() => setHovered(node.id)}
              onMouseLeave={() => setHovered(null)}
              style={{ cursor: 'pointer' }}
            >
              <rect
                x={node.x} y={node.y}
                width={node.w} height={node.h}
                rx={8}
                fill={node.color}
                opacity={hovered === node.id ? 1 : node.dashed ? 0.15 : 0.9}
                stroke={node.color}
                strokeWidth={node.dashed ? 1 : 0}
                strokeDasharray={node.dashed ? '4,3' : 'none'}
              />
              <text
                x={node.x + node.w / 2}
                y={node.y + node.h / 2 + 4}
                textAnchor="middle"
                fontSize="12"
                fontWeight="600"
                fill={node.dashed ? node.color : node.textColor}
              >
                {node.label}
              </text>
            </g>
          ))}

          {/* Legend */}
          <g transform="translate(20, 430)">
            <rect x={0} y={0} width={500} height={40} rx={6} fill="#1e293b" opacity={0.6} />
            <text x={10} y={16} fontSize="11" fill="#94a3b8" fontWeight="600">Legend:</text>
            <line x1={70} y1={10} x2={100} y2={10} stroke="#475569" strokeWidth={2} markerEnd="url(#arrow)" />
            <text x={105} y={14} fontSize="10" fill="#94a3b8">Normal flow</text>
            <line x1={200} y1={10} x2={230} y2={10} stroke="#ef4444" strokeWidth={1.5} strokeDasharray="4,3" markerEnd="url(#arrow-red)" />
            <text x={235} y={14} fontSize="10" fill="#94a3b8">Fail path</text>
            <line x1={300} y1={10} x2={330} y2={10} stroke="#f59e0b" strokeWidth={1.5} strokeDasharray="4,3" markerEnd="url(#arrow-yellow)" />
            <text x={335} y={14} fontSize="10" fill="#94a3b8">Retry loop</text>
            <text x={10} y={34} fontSize="10" fill="#64748b">Dashed boxes = infrastructure components (ChromaDB, LangSmith, LLM)</text>
          </g>
        </svg>
      </div>

      {/* Components Description */}
      <div className="arch-components">
        {[
          { icon: '🗄️', name: 'ChromaDB', desc: 'Local vector store with sentence-transformer embeddings (all-MiniLM-L6-v2)' },
          { icon: '⚖️', name: 'Relevance Grader', desc: 'LLM-as-judge scores context 0–1. Below threshold triggers query rewrite.' },
          { icon: '✏️', name: 'Query Rewriter', desc: 'Reformulates query for better technical document retrieval. Max 2 retries.' },
          { icon: '🔬', name: 'Groundedness Check', desc: 'Verifies generation is supported by context. Flags hallucinations.' },
          { icon: '🛡️', name: 'Guardrail', desc: 'Blocks answers that give instructions for hardware not mentioned in context.' },
          { icon: '📡', name: 'LangSmith', desc: 'Full distributed tracing of all LLM calls, decisions, and scores.' },
        ].map(c => (
          <div key={c.name} className="arch-component-item">
            <span className="arch-component-icon">{c.icon}</span>
            <div>
              <strong>{c.name}</strong>
              <p>{c.desc}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
