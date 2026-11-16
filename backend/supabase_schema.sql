-- ==========================================================
--  ATLAS AI v3.0 - SCHEMA SUPABASE COMPLETO E PRODUZIONE
--  Copia questo intero script nell'SQL Editor di Supabase
--  ed eseguilo per creare/aggiornare le tabelle necessarie.
-- ==========================================================

-- Estensione UUID (di default già presente in Supabase, ma per sicurezza)
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ==========================================================
--  1. Profili famiglia (PIN ora salvati come hash bcrypt)
-- ==========================================================
CREATE TABLE IF NOT EXISTS profiles (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    slug VARCHAR(50) UNIQUE NOT NULL,           -- es. 'io', 'mamma', 'papa'
    nome VARCHAR(100) NOT NULL,
    lingua_madre VARCHAR(50) DEFAULT 'Italiano',
    livello_italiano VARCHAR(20) DEFAULT 'C1',
    pin_hash VARCHAR(255),                       -- bcrypt hash del PIN
    punti_famiglia INTEGER DEFAULT 0,
    streak_giorni INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- Trigger per mantenere updated_at aggiornato
DO $$ BEGIN
    CREATE OR REPLACE FUNCTION trigger_set_timestamp()
    RETURNS TRIGGER AS $$
    BEGIN
        NEW.updated_at = timezone('utc'::text, now());
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
EXCEPTION WHEN OTHERS THEN NULL; END $$;

DROP TRIGGER IF EXISTS set_timestamp_profiles ON profiles;
CREATE TRIGGER set_timestamp_profiles
BEFORE UPDATE ON profiles
FOR EACH ROW EXECUTE FUNCTION trigger_set_timestamp();

-- Seed profili standard (pin_hash = bcrypt dei PIN di default, da cambiare in produzione!)
INSERT INTO profiles (slug, nome, lingua_madre, livello_italiano, pin_hash) VALUES
    ('io',         'Tu (Admin)',    'Italiano', 'C1',         '$2b$12$3H35nZSLzP2KdIhJqjKsAu/dEHhIFS8PGhti0kpd6pdOSreO5rx7y'), -- 0000
    ('mamma',      'Mamma',         'Albanese', 'B1',         '$2b$12$W0ULwtx0rEHNM0mUsZHrUuEWjpcqSlnOQIKSdfZdBPgprSNst0D4G'), -- 1111
    ('papa',       'Papà',          'Albanese', 'A2',         '$2b$12$4zsGd6Qz14tNEpXEwmvnkuqWdMTuyAVKmAYtu/rR23.mrmro8uMVC'), -- 2222
    ('fratello1',  'Fratello 1',    'Italiano', 'Madrelingua','$2b$12$aYuNTtNhF.EFpozA9fhoXe/p3/UvKENZy3E/tQbhT1ZtBFa58DQkG'), -- 3333
    ('fratello2',  'Fratello 2',    'Italiano', 'Madrelingua','$2b$12$07nQ0IAXtns1ofaUmvXIVeQU3u2jg3q7nTT4x9NzjL3hH54DRblua')  -- 4444
ON CONFLICT (slug) DO NOTHING;


-- ==========================================================
--  2. Messaggi (memoria RAG di Gemini)
--     ⚠️ Nota: la colonna si chiama 'profile_slug' NON 'user_id'
-- ==========================================================
CREATE TABLE IF NOT EXISTS messages (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    profile_slug VARCHAR(50) NOT NULL REFERENCES profiles(slug) ON DELETE CASCADE,
    role VARCHAR(10) NOT NULL CHECK (role IN ('user', 'ai')),
    content TEXT NOT NULL,
    tokens_consumed INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_messages_profile_created
    ON messages(profile_slug, created_at DESC);


-- ==========================================================
--  3. Todos condivisi / lista della spesa
-- ==========================================================
CREATE TABLE IF NOT EXISTS family_todos (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    task_text TEXT NOT NULL,
    assegnato_a VARCHAR(100) DEFAULT 'Tutti',
    created_by_slug VARCHAR(50) REFERENCES profiles(slug),
    is_completed BOOLEAN DEFAULT FALSE,
    completed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_todos_completed
    ON family_todos(is_completed, created_at DESC);


-- ==========================================================
--  4. Spese / Budget famigliare
-- ==========================================================
CREATE TABLE IF NOT EXISTS family_expenses (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    amount DECIMAL(12,2) NOT NULL CHECK (amount > 0),
    category VARCHAR(50) NOT NULL,
    description VARCHAR(500),
    created_by_slug VARCHAR(50) REFERENCES profiles(slug),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_expenses_category_created
    ON family_expenses(category, created_at DESC);


-- ==========================================================
--  5. Storico lezioni / progresso italiano
-- ==========================================================
CREATE TABLE IF NOT EXISTS italian_progress (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    profile_slug VARCHAR(50) NOT NULL REFERENCES profiles(slug) ON DELETE CASCADE,
    lezione_id VARCHAR(100),
    punteggio INTEGER DEFAULT 0,
    completato BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);


-- ==========================================================
--  6. Tokens push notifiche (Expo Push / Firebase)
-- ==========================================================
CREATE TABLE IF NOT EXISTS push_tokens (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    profile_slug VARCHAR(50) NOT NULL REFERENCES profiles(slug) ON DELETE CASCADE,
    token VARCHAR(255) UNIQUE NOT NULL,
    device_info VARCHAR(255),
    platform VARCHAR(20) DEFAULT '',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- Migrazione per installazioni già esistenti
ALTER TABLE push_tokens ADD COLUMN IF NOT EXISTS platform VARCHAR(20) DEFAULT '';


-- ==========================================================
--  7. Promemoria personali (creati dalla chat / scheduler)
-- ==========================================================
CREATE TABLE IF NOT EXISTS family_reminders (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    profile_slug VARCHAR(50) NOT NULL REFERENCES profiles(slug) ON DELETE CASCADE,
    message TEXT NOT NULL,
    remind_at TIMESTAMP WITH TIME ZONE NOT NULL,
    include_todos BOOLEAN DEFAULT TRUE,
    status VARCHAR(20) DEFAULT 'pending' CHECK (status IN ('pending', 'sent', 'cancelled')),
    source VARCHAR(30) DEFAULT 'chat',
    local_scheduled_at TIMESTAMP WITH TIME ZONE,
    sent_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_reminders_profile_time
    ON family_reminders(profile_slug, status, remind_at);

-- Migrazioni per installazioni che avevano già la tabella senza questi campi.
ALTER TABLE family_reminders ADD COLUMN IF NOT EXISTS local_scheduled_at TIMESTAMP WITH TIME ZONE;
ALTER TABLE family_reminders ADD COLUMN IF NOT EXISTS sent_at TIMESTAMP WITH TIME ZONE;
ALTER TABLE family_reminders ADD COLUMN IF NOT EXISTS source VARCHAR(30) DEFAULT 'chat';


-- ==========================================================
--  8. Impostazioni applicazione (automazioni, notifiche, soglie)
-- ==========================================================
CREATE TABLE IF NOT EXISTS app_settings (
    key TEXT PRIMARY KEY,
    value JSONB NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);


-- ==========================================================
--  9. Token revocati (logout reale, denylist fino a scadenza)
-- ==========================================================
CREATE TABLE IF NOT EXISTS revoked_tokens (
    token_hash TEXT PRIMARY KEY,
    expires_at BIGINT NOT NULL,
    revoked_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_revoked_tokens_expires ON revoked_tokens(expires_at);


-- ==========================================================
--  ROW LEVEL SECURITY (opzionale, buono per produzione)
-- ==========================================================
-- ALTER TABLE profiles ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE messages ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE family_todos ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE family_expenses ENABLE ROW LEVEL SECURITY;

-- Per il backend usiamo la SERVICE ROLE KEY che bypassa RLS.
-- Il frontend userà la ANON KEY + policy custom (da definire caso per caso).
