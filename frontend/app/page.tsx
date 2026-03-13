"use client";

import { useState } from "react";

type AlchemyResponse = {
  idea: string;
  mode: string;
  intent: string;
  problem: string;
  solution: string;
  tech_stack: string[];
  roadmap: string[];
  risks: string[];
};

export default function Home() {
  const [idea, setIdea] = useState("");
  const [mode, setMode] = useState("build");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<AlchemyResponse | null>(null);
  const [error, setError] = useState("");

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError("");
    setResult(null);

    try {
      const response = await fetch("http://127.0.0.1:8000/api/v1/alchemy/run", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          idea,
          mode,
        }),
      });

      if (!response.ok) {
        throw new Error("Request failed");
      }

      const data = await response.json();
      setResult(data);
    } catch {
      setError("Could not reach Alchemind backend.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="min-h-screen bg-white text-black p-8">
      <div className="mx-auto max-w-4xl">
        <h1 className="mb-2 text-4xl font-bold">Alchemind</h1>
        <p className="mb-8 text-gray-600">Turn ideas into executable systems.</p>

        <form onSubmit={handleSubmit} className="mb-8 space-y-4">
          <div>
            <label className="mb-2 block font-medium">Your idea</label>
            <textarea
              className="min-h-32 w-full rounded-xl border p-4"
              value={idea}
              onChange={(e) => setIdea(e.target.value)}
              placeholder="Build an AI personal executive assistant for students"
            />
          </div>

          <div>
            <label className="mb-2 block font-medium">Mode</label>
            <select
              className="rounded-xl border p-3"
              value={mode}
              onChange={(e) => setMode(e.target.value)}
            >
              <option value="build">build</option>
              <option value="startup">startup</option>
              <option value="research">research</option>
            </select>
          </div>

          <button
            type="submit"
            disabled={loading || !idea.trim()}
            className="rounded-xl bg-black px-6 py-3 text-white disabled:opacity-50"
          >
            {loading ? "Transmuting..." : "Run Alchemind"}
          </button>
        </form>

        {error && (
          <div className="mb-6 rounded-xl border border-red-300 bg-red-50 p-4 text-red-700">
            {error}
          </div>
        )}

        {result && (
          <div className="space-y-6">
            <section className="rounded-2xl border p-5">
              <h2 className="mb-3 text-xl font-semibold">Core Output</h2>
              <p><strong>Idea:</strong> {result.idea}</p>
              <p><strong>Mode:</strong> {result.mode}</p>
              <p><strong>Intent:</strong> {result.intent}</p>
            </section>

            <section className="rounded-2xl border p-5">
              <h2 className="mb-3 text-xl font-semibold">Problem</h2>
              <p>{result.problem}</p>
            </section>

            <section className="rounded-2xl border p-5">
              <h2 className="mb-3 text-xl font-semibold">Solution</h2>
              <p>{result.solution}</p>
            </section>

            <section className="rounded-2xl border p-5">
              <h2 className="mb-3 text-xl font-semibold">Tech Stack</h2>
              <ul className="list-disc space-y-1 pl-6">
                {result.tech_stack.map((item, index) => (
                  <li key={index}>{item}</li>
                ))}
              </ul>
            </section>

            <section className="rounded-2xl border p-5">
              <h2 className="mb-3 text-xl font-semibold">Roadmap</h2>
              <ol className="list-decimal space-y-1 pl-6">
                {result.roadmap.map((item, index) => (
                  <li key={index}>{item}</li>
                ))}
              </ol>
            </section>

            <section className="rounded-2xl border p-5">
              <h2 className="mb-3 text-xl font-semibold">Risks</h2>
              <ul className="list-disc space-y-1 pl-6">
                {result.risks.map((item, index) => (
                  <li key={index}>{item}</li>
                ))}
              </ul>
            </section>
          </div>
        )}
      </div>
    </main>
  );
}