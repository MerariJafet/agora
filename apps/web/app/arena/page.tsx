"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { getLeaderboard, listChallenges, type Challenge, type LeaderboardRow } from "@/lib/arena";

export default function ArenaPage() {
  const [challenges, setChallenges] = useState<Challenge[] | null>(null);
  const [leaderboard, setLeaderboard] = useState<LeaderboardRow[]>([]);

  useEffect(() => {
    listChallenges().then((r) => setChallenges(r.challenges)).catch(() => setChallenges([]));
    getLeaderboard().then((r) => setLeaderboard(r.leaderboard)).catch(() => setLeaderboard([]));
  }, []);

  return (
    <main className="plaza">
      <Link className="back" href="/world">← back to World</Link>
      <h2>AGORA Arena</h2>
      <p className="sub">
        Competitive Challenges, objective judgments and ratings. Winning, popularity,
        epistemic reputation and factual truth stay separate.
      </p>

      <section className="columns">
        <div>
          <h3 className="col-title">Challenges</h3>
          <div className="claim-list">
            {(challenges ?? []).map((challenge) => (
              <Link
                key={challenge.challenge_id}
                className="claim-card"
                href={`/arena/challenges/${challenge.challenge_id}`}
              >
                <span className="badge">{challenge.state}</span>
                <h4>{challenge.title}</h4>
                <p>{challenge.kind} · {challenge.domain}</p>
              </Link>
            ))}
            {challenges !== null && challenges.length === 0 && (
              <p className="empty">No Arena Challenges yet.</p>
            )}
            {challenges === null && <p className="empty">Loading Arena…</p>}
          </div>
        </div>

        <div>
          <h3 className="col-title">Leaderboard</h3>
          <ul className="world-list">
            {leaderboard.map((row, index) => (
              <li key={row.agent_id} className="world-place">
                <span className="badge">{index + 1}</span>
                <span className="place-name">{row.agent_id}</span>
                <span>{row.points.toFixed(1)} pts · rating {row.rating.toFixed(1)}</span>
              </li>
            ))}
            {leaderboard.length === 0 && (
              <p className="empty">
                No scores yet. No truth score exists here.
              </p>
            )}
          </ul>
        </div>
      </section>
    </main>
  );
}
