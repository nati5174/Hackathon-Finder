import { useEffect, useState } from "react";

const MONTHS = { JAN:1,FEB:2,MAR:3,APR:4,MAY:5,JUN:6,JUL:7,AUG:8,SEP:9,OCT:10,NOV:11,DEC:12 };

function parseDateNum(dateStr) {
  const match = (dateStr || "").match(/([A-Z]+)\s+(\d+)/);
  if (!match) return 0;
  const month = MONTHS[match[1]] || 0;
  const day = parseInt(match[2]);
  // MLH 2026 season: JUL–DEC are 2025, JAN–JUN are 2026
  const year = month >= 7 ? 2025 : 2026;
  return year * 10000 + month * 100 + day;
}

function sortByDate(hackathons) {
  const now = new Date();
  const todayNum = now.getFullYear() * 10000 + (now.getMonth() + 1) * 100 + now.getDate();
  const upcoming = hackathons.filter(h => parseDateNum(h.date_str) >= todayNum)
    .sort((a, b) => parseDateNum(a.date_str) - parseDateNum(b.date_str));
  const past = hackathons.filter(h => parseDateNum(h.date_str) < todayNum)
    .sort((a, b) => parseDateNum(b.date_str) - parseDateNum(a.date_str));
  return [...upcoming, ...past];
}

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

  const now = new Date();
  const todayNum = now.getFullYear() * 10000 + (now.getMonth() + 1) * 100 + now.getDate();

  const upcomingWithTravel = sortByDate(allHackathons.filter((h) => h.travel_reimbursement && matches(h) && parseDateNum(h.date_str) >= todayNum));
  const upcomingOther = sortByDate(allHackathons.filter((h) => !h.travel_reimbursement && !h.skipped && matches(h) && parseDateNum(h.date_str) >= todayNum));
  const pastWithTravel = sortByDate(allHackathons.filter((h) => h.travel_reimbursement && matches(h) && parseDateNum(h.date_str) < todayNum));

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
            <h3 className="section-title">Upcoming — Travel Reimbursement Available</h3>
            {upcomingWithTravel.length === 0 ? (
              <p className="empty">
                {stats && stats.total === 0
                  ? "The daily scrape hasn't run yet — check back soon."
                  : "No upcoming hackathons with travel reimbursement found yet."}
              </p>
            ) : (
              <div className="grid">
                {upcomingWithTravel.map((h) => (
                  <HackathonCard key={h.id} h={h} highlight={true} />
                ))}
              </div>
            )}
          </section>

          {pastWithTravel.length > 0 && (
            <section>
              <h3 className="section-title">Past — Travel Reimbursement Offered</h3>
              <div className="grid">
                {pastWithTravel.map((h) => (
                  <HackathonCard key={h.id} h={h} highlight={true} />
                ))}
              </div>
            </section>
          )}

          {upcomingOther.length > 0 && (
            <section className="section-dim">
              <h3 className="section-title dim">Upcoming — Other MLH Hackathons</h3>
              <div className="grid">
                {upcomingOther.map((h) => (
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
