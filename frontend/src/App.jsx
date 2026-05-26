import { useEffect, useState } from "react";

const MONTHS = { JAN:1,FEB:2,MAR:3,APR:4,MAY:5,JUN:6,JUL:7,AUG:8,SEP:9,OCT:10,NOV:11,DEC:12 };

function currentSeason() {
  const now = new Date();
  return now.getMonth() < 6 ? now.getFullYear() : now.getFullYear() + 1;
}

function parseDateNum(dateStr, season) {
  const match = (dateStr || "").match(/([A-Z]+)\s+(\d+)/);
  if (!match) return 0;
  const month = MONTHS[match[1]] || 0;
  const day = parseInt(match[2]);
  const year = month >= 7 ? season - 1 : season;
  return year * 10000 + month * 100 + day;
}

function sortByDate(hackathons, season) {
  const now = new Date();
  const todayNum = now.getFullYear() * 10000 + (now.getMonth() + 1) * 100 + now.getDate();
  const upcoming = hackathons.filter(h => parseDateNum(h.date_str, season) >= todayNum)
    .sort((a, b) => parseDateNum(a.date_str, season) - parseDateNum(b.date_str, season));
  const past = hackathons.filter(h => parseDateNum(h.date_str, season) < todayNum)
    .sort((a, b) => parseDateNum(b.date_str, season) - parseDateNum(a.date_str, season));
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

function SubscribeForm() {
  const [email, setEmail] = useState("");
  const [status, setStatus] = useState(null); // null | "loading" | "success" | "error"
  const [message, setMessage] = useState("");

  const handleSubmit = async (e) => {
    e.preventDefault();
    setStatus("loading");
    try {
      const res = await fetch("/api/subscribe", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email }),
      });
      const data = await res.json();
      setMessage(data.message);
      setStatus("success");
      setEmail("");
    } catch {
      setMessage("Something went wrong. Please try again.");
      setStatus("error");
    }
  };

  return (
    <form className="subscribe-form" onSubmit={handleSubmit}>
      <p className="subscribe-label">Get notified of new hackathons</p>
      <div className="subscribe-row">
        <input
          type="email"
          placeholder="your@email.com"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
          disabled={status === "loading"}
        />
        <button type="submit" disabled={status === "loading"}>
          {status === "loading" ? "Sending..." : "Notify Me"}
        </button>
      </div>
      {message && <p className={`subscribe-msg ${status}`}>{message}</p>}
    </form>
  );
}

export default function App() {
  const [allHackathons, setAllHackathons] = useState([]);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [search, setSearch] = useState("");

  useEffect(() => {
    Promise.all([
      fetch("/api/hackathons/all").then((r) => r.json()),
      fetch("/api/stats").then((r) => r.json()),
    ]).then(([data, statsData]) => {
      setAllHackathons(data);
      setStats(statsData);
      setLoading(false);
    }).catch((err) => {
      setError(err.message || "Failed to load hackathons.");
      setLoading(false);
    });
  }, []);

  const matches = (h) =>
    h.name.toLowerCase().includes(search.toLowerCase()) ||
    h.location.toLowerCase().includes(search.toLowerCase());

  const season = currentSeason();
  const now = new Date();
  const todayNum = now.getFullYear() * 10000 + (now.getMonth() + 1) * 100 + now.getDate();

  const upcomingWithTravel = sortByDate(allHackathons.filter((h) => h.travel_reimbursement && matches(h) && parseDateNum(h.date_str, season) >= todayNum), season);
  const upcomingOther = sortByDate(allHackathons.filter((h) => !h.travel_reimbursement && !h.skipped && matches(h) && parseDateNum(h.date_str, season) >= todayNum), season);
  const pastWithTravel = sortByDate(allHackathons.filter((h) => h.travel_reimbursement && matches(h) && parseDateNum(h.date_str, season) < todayNum), season);

  return (
    <div className="container">
      <header>
        <div className="header-left">
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
        </div>
        <SubscribeForm />
      </header>

      <input
        className="search"
        type="text"
        placeholder="Search by name or location..."
        value={search}
        onChange={(e) => setSearch(e.target.value)}
      />

      {loading && <p className="loading">Loading hackathons...</p>}
      {error && <p className="loading">Error: {error}</p>}

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
