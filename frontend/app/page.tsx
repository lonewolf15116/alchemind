"use client";

import { useState } from "react";

interface AlchemyResult {
  problem?: string;
  solution?: string;
  tech_stack?: any[];
  roadmap?: any[];
  risks?: any[];
  success_metrics?: any[];
  differentiation?: any[];
  monetization?: any[];
  go_to_market?: any[];
  architecture?: any;
}

export default function Home() {
  const [idea, setIdea] = useState("");
  const [mode, setMode] = useState("build");
  const [result, setResult] = useState<AlchemyResult | null>(null);
  const [loading, setLoading] = useState(false);

  async function runAlchemy() {
    if (!idea.trim()) return;

    setLoading(true);
    setResult(null);

    const apiUrl =
      process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

    try {
      const res = await fetch(`${apiUrl}/api/v1/alchemy/run`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ idea, mode }),
      });

      if (!res.ok) throw new Error(`HTTP ${res.status}`);

      const data: AlchemyResult = await res.json();
      setResult(data);
    } catch (error) {
      console.error(error);
      setResult({
        problem: "Backend not reachable",
        solution: `Ensure FastAPI is running on ${apiUrl}`,
      });
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="min-h-screen bg-black px-6 py-10 text-white">
      <div className="mx-auto max-w-6xl">

        {/* HEADER */}
        <div className="mb-12">
          <div className="mb-4 flex items-center gap-2">
            <div className="h-2 w-2 rounded-full bg-white/70" />
            <span className="text-sm font-semibold text-white/80">
              Alchemind
            </span>
          </div>

          <h1 className="mb-4 text-4xl font-semibold md:text-5xl">
            Turn ideas into executable systems
          </h1>

          <p className="text-white/60">
            AI system for product thinking, execution, and strategy.
          </p>
        </div>

        {/* INPUT */}
        <div className="mb-8 rounded-2xl border border-white/10 bg-white/5 p-6">
          <textarea
            value={idea}
            onChange={(e) => setIdea(e.target.value)}
            placeholder="Enter your idea..."
            className="mb-4 h-32 w-full rounded-xl border border-white/10 bg-black/30 p-4"
          />

          <div className="flex gap-3">
            <select
              value={mode}
              onChange={(e) => setMode(e.target.value)}
              className="rounded-xl bg-black/30 px-4 py-2"
            >
              <option value="build">build</option>
              <option value="startup">startup</option>
              <option value="research">research</option>
            </select>

            <button
              onClick={runAlchemy}
              className="rounded-xl bg-white px-6 py-2 text-black"
            >
              {loading ? "Thinking..." : "Run"}
            </button>
          </div>
        </div>

        {/* LOADING */}
        {loading && (
          <div className="mb-6 text-white/60">
            Analyzing → Structuring → Generating system...
          </div>
        )}

        {/* OUTPUT */}
        {result && (
          <div className="space-y-8">

            <Card title="Problem" content={result.problem} />
            <Card title="Solution" content={result.solution} />

            <ListCard title="Why We Win" items={result.differentiation} />
            <ListCard title="Success Metrics" items={result.success_metrics} />
            <ListCard title="Business Model" items={result.monetization} />
            <ListCard title="Go-To-Market" items={result.go_to_market} />
            <ListCard title="Tech Stack" items={result.tech_stack} />
            <ListCard title="Roadmap" items={result.roadmap} />

            <Card
              title="System Architecture"
              content={renderArchitecture(result.architecture)}
            />

            <ListCard title="Risks" items={result.risks} />

          </div>
        )}
      </div>
    </main>
  );
}

/* ---------- COMPONENTS ---------- */

function Card({ title, content }: any) {
  if (!content) return null;

  return (
    <div className="rounded-xl border border-white/10 p-4">
      <h2 className="mb-2 font-semibold">{title}</h2>

      <div className="text-white/70 text-sm leading-7">
        {typeof content === "string" ? <p>{content}</p> : content}
      </div>
    </div>
  );
}

function ListCard({ title, items }: any) {
  if (!items || items.length === 0) return null;

  return (
    <div className="rounded-xl border border-white/10 p-4">
      <h2 className="mb-3 font-semibold">{title}</h2>

      <div className="space-y-3">

        {items.map((item: any, idx: number) => {

          // STRING
          if (typeof item === "string") {
            return <p key={idx}>• {item}</p>;
          }

          // OBJECT (ROADMAP FIX)
          if (typeof item === "object" && item !== null) {
            return (
              <div key={idx} className="border border-white/10 p-3 rounded">

                {item.phase && (
                  <p className="font-semibold">{item.phase}</p>
                )}

                {item.duration && (
                  <p className="text-xs text-white/50">{item.duration}</p>
                )}

                {item.deliverables && (
                  <ul className="list-disc pl-5 mt-2">
                    {item.deliverables.map((d: string, i: number) => (
                      <li key={i}>{d}</li>
                    ))}
                  </ul>
                )}
              </div>
            );
          }

          return null;
        })}

      </div>
    </div>
  );
}

function renderArchitecture(arch: any) {
  if (!arch) return null;

  if (typeof arch === "string") {
    return <span>{arch}</span>; // ✅ FIXED (no nested <p>)
  }

  return (
    <pre className="text-xs whitespace-pre-wrap">
      {JSON.stringify(arch, null, 2)}
    </pre>
  );
}