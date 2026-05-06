-- ============================================================================
--  Lumora Code — Client Pipeline · Supabase migration
-- ----------------------------------------------------------------------------
--  Run this ONCE in the Supabase SQL editor:
--      Dashboard → SQL Editor → New query → paste this whole file → Run.
--
--  After it succeeds, populate the database password in the Lumora desktop
--  app (Settings → Supabase Database → DB password) and you're done.
--
--  Idempotent — safe to re-run; it uses IF NOT EXISTS guards everywhere.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1. Enums
-- ----------------------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'leadstatus') THEN
        CREATE TYPE leadstatus AS ENUM (
            'FOUND', 'RESEARCHED', 'CONTACTED', 'RESPONDED',
            'CALL_BOOKED', 'PROPOSAL_SENT', 'CLOSED_WON', 'CLOSED_LOST'
        );
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'outreachchannel') THEN
        CREATE TYPE outreachchannel AS ENUM (
            'EMAIL', 'COLD_CALL', 'LINKEDIN_DM',
            'INSTAGRAM_DM', 'FACEBOOK_DM', 'WHATSAPP'
        );
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'scrapejobstatus') THEN
        CREATE TYPE scrapejobstatus AS ENUM (
            'PENDING', 'RUNNING', 'COMPLETED', 'FAILED'
        );
    END IF;
END $$;

-- ----------------------------------------------------------------------------
-- 2. Tables
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.leads (
    id                      SERIAL PRIMARY KEY,
    business_name           VARCHAR(300) NOT NULL,
    owner_name              VARCHAR(200),
    industry                VARCHAR(100) NOT NULL,
    category                VARCHAR(200),
    address                 VARCHAR(500),
    city                    VARCHAR(100) NOT NULL,
    country                 VARCHAR(100) NOT NULL,
    phone                   VARCHAR(50),
    emails                  JSONB,
    website_url             VARCHAR(500),
    has_website             BOOLEAN NOT NULL DEFAULT FALSE,
    google_maps_url         VARCHAR(500),
    google_rating           DOUBLE PRECISION,
    google_reviews          INTEGER,
    social_links            JSONB,
    website_quality_score   DOUBLE PRECISION,
    website_issues          JSONB,
    screenshot_path         VARCHAR(500),
    lead_score              DOUBLE PRECISION,
    ai_research             JSONB,
    status                  leadstatus NOT NULL DEFAULT 'FOUND',
    source                  VARCHAR(200),
    notes                   TEXT,
    next_action             VARCHAR(300),
    next_action_date        TIMESTAMP,
    created_at              TIMESTAMP NOT NULL DEFAULT (NOW() AT TIME ZONE 'utc'),
    updated_at              TIMESTAMP NOT NULL DEFAULT (NOW() AT TIME ZONE 'utc')
);

CREATE INDEX IF NOT EXISTS ix_leads_business_name ON public.leads (business_name);
CREATE INDEX IF NOT EXISTS ix_leads_industry      ON public.leads (industry);
CREATE INDEX IF NOT EXISTS ix_leads_city          ON public.leads (city);
CREATE INDEX IF NOT EXISTS ix_leads_country       ON public.leads (country);
CREATE INDEX IF NOT EXISTS ix_leads_status        ON public.leads (status);

CREATE TABLE IF NOT EXISTS public.outreach_logs (
    id          SERIAL PRIMARY KEY,
    lead_id     INTEGER NOT NULL REFERENCES public.leads(id) ON DELETE CASCADE,
    channel     outreachchannel NOT NULL,
    subject     VARCHAR(300),
    content     TEXT NOT NULL,
    response    TEXT,
    sent_at     TIMESTAMP NOT NULL DEFAULT (NOW() AT TIME ZONE 'utc')
);

CREATE INDEX IF NOT EXISTS ix_outreach_logs_lead_id ON public.outreach_logs (lead_id);

CREATE TABLE IF NOT EXISTS public.scrape_jobs (
    id              SERIAL PRIMARY KEY,
    query           VARCHAR(300) NOT NULL,
    industry        VARCHAR(100) NOT NULL,
    city            VARCHAR(100) NOT NULL,
    country         VARCHAR(100) NOT NULL,
    status          scrapejobstatus NOT NULL DEFAULT 'PENDING',
    results_count   INTEGER NOT NULL DEFAULT 0,
    error_message   TEXT,
    started_at      TIMESTAMP NOT NULL DEFAULT (NOW() AT TIME ZONE 'utc'),
    completed_at    TIMESTAMP
);

-- ----------------------------------------------------------------------------
-- 3. Auto-update `updated_at` on every row update
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.touch_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW() AT TIME ZONE 'utc';
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS leads_touch_updated_at ON public.leads;
CREATE TRIGGER leads_touch_updated_at
    BEFORE UPDATE ON public.leads
    FOR EACH ROW
    EXECUTE FUNCTION public.touch_updated_at();

-- ----------------------------------------------------------------------------
-- 4. Row-Level Security
-- ----------------------------------------------------------------------------
-- The Lumora desktop app talks to Postgres directly using the database
-- password (postgres user → bypasses RLS by default), so RLS does not
-- affect normal app traffic. We still enable + leave wide-open policies
-- so the publishable/anon REST endpoints work too if you ever need them.
-- Replace these policies with stricter ones once you add real auth.
-- ----------------------------------------------------------------------------
ALTER TABLE public.leads          ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.outreach_logs  ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.scrape_jobs    ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "lumora_leads_all"         ON public.leads;
DROP POLICY IF EXISTS "lumora_outreach_all"      ON public.outreach_logs;
DROP POLICY IF EXISTS "lumora_scrape_jobs_all"   ON public.scrape_jobs;

CREATE POLICY "lumora_leads_all"
    ON public.leads
    FOR ALL
    USING (true) WITH CHECK (true);

CREATE POLICY "lumora_outreach_all"
    ON public.outreach_logs
    FOR ALL
    USING (true) WITH CHECK (true);

CREATE POLICY "lumora_scrape_jobs_all"
    ON public.scrape_jobs
    FOR ALL
    USING (true) WITH CHECK (true);

-- Done.  Verify with:
--   SELECT count(*) FROM public.leads;          -- should return 0
--   SELECT count(*) FROM public.outreach_logs;  -- should return 0
--   SELECT count(*) FROM public.scrape_jobs;    -- should return 0
