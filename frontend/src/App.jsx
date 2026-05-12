import { useEffect, useState } from "react";

function HackathonCard({ h, highlight }) {
  return (
    <a
      href={h.hackathon_url}
      target="_blank"
      rel="noopener noreferrer"
      className={`card ${highlight ? "card-highlight" : "card-dim"}`}
    >
      <div className="card-top">
        <h2>{h.name}</h2>
        {highlight && <span className="badge">Travel covered</span>}
      </div>
      <p className="location">{h.location}</p>
      <p className="date">{h.date_str}</p>
      {h.travel_details && <p className="details">{h.travel_details}</p>}
    </a>
  );
}

export default function App() {
  const [allHackathons, setAllHackathons] = useState([]);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");

  useEffect(() => {
    Promise.all([
      fetch("/api/hackathons/all").then((r) => r.json()),
      fetch("/api/stats").then((r) => r.json()),
    ]).then(([data, statsData]) => {
      setAllHackathons(data);
      setStats(statsData);
      setLoading(false);
    });
  }, []);

  const matches = (h) =>
    h.name.toLowerCase().includes(search.toLowerCase()) ||
    h.location.toLowerCase().includes(search.toLowerCase());

  const withTravel = allHackathons.filter((h) => h.travel_reimbursement && matches(h));
  const withoutTravel = allHackathons.filter((h) => !h.travel_reimbursement && !h.skipped && matches(h));

  return (
    <div className="container">
      <header>
        <h1>Hackathon Travel Finder</h1>
        <p className="subtitle">
          Hackathons from MLH that cover your travel — fly for free.
        </p>
        {stats && (
          <p className="stats">
            {stats.with_travel_reimbursement} with travel reimbursement out of{" "}
            {stats.total} checked &mdash; last updated{" "}
            {stats.last_updated
              ? new Date(stats.last_updated).toLocaleDateString()
              : "never"}
          </p>
        )}
      </header>

      <input
        className="search"
        type="text"
        placeholder="Search by name or location..."
        value={search}
        onChange={(e) => setSearch(e.target.value)}
      />

      {loading && <p className="loading">Loading hackathons...</p>}

      {!loading && (
        <>
          <section>
            <h3 className="section-title">Travel Reimbursement Available</h3>
            {withTravel.length === 0 ? (
              <p className="empty">
                {stats && stats.total === 0
                  ? "The daily scrape hasn't run yet — check back soon."
                  : "No hackathons with travel reimbursement found yet. Check back as more are added to the season."}
              </p>
            ) : (
              <div className="grid">
                {withTravel.map((h) => (
                  <HackathonCard key={h.id} h={h} highlight={true} />
                ))}
              </div>
            )}
          </section>

          {withoutTravel.length > 0 && (
            <section className="section-dim">
              <h3 className="section-title dim">Other MLH Hackathons</h3>
              <div className="grid">
                {withoutTravel.map((h) => (
                  <HackathonCard key={h.id} h={h} highlight={false} />
                ))}
              </div>
            </section>
          )}
        </>
      )}
    </div>
  );
}
