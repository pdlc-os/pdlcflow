export function AdminLive() {
  return (
    <div>
      <h2 className="mb-2 text-lg font-semibold">Live</h2>
      <p className="text-sm text-muted-fg">
        Real-time event feed across every squad in the org. Backed by Redis Pub/Sub samples
        plus rolling ClickHouse queries. Wired in Phase G.
      </p>
    </div>
  );
}
