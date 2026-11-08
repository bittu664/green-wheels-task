CREATE TABLE IF NOT EXISTS lease_sequence (
    driver_id text PRIMARY KEY,
    version bigint NOT NULL
);
CREATE TABLE IF NOT EXISTS facts (
    event_id uuid PRIMARY KEY,
    driver_id text NOT NULL,
    event_type text NOT NULL,
    version bigint NOT NULL,
    request_id text NOT NULL,
    accepted_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    published_at timestamptz,
    projected_at timestamptz,
    scored boolean NOT NULL DEFAULT false,
    UNIQUE(driver_id, version)
);
CREATE INDEX IF NOT EXISTS unpublished ON facts (accepted_at) WHERE published_at IS NULL;
CREATE INDEX IF NOT EXISTS unscored ON facts (accepted_at)
    WHERE NOT scored AND event_type = 'payment_made';
CREATE INDEX IF NOT EXISTS pending ON facts (accepted_at) WHERE projected_at IS NULL;
CREATE TABLE IF NOT EXISTS lease_view (
    driver_id text PRIMARY KEY,
    status text NOT NULL,
    payment_cycle integer NOT NULL,
    version bigint NOT NULL
);
CREATE TABLE IF NOT EXISTS freshness_totals (
    outcome text PRIMARY KEY,
    total bigint NOT NULL DEFAULT 0
);
INSERT INTO freshness_totals(outcome) VALUES ('good'), ('bad') ON CONFLICT DO NOTHING;
