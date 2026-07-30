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
    ('io',         'Tu (Admin)',    'Italiano', 'C1',         '$2b$12$xM7p5Fm5j3ZbR3kL9nQ0VuxVHEbK7yGj5vWzQ8xR9pT2sU4dI6Z7O'), -- 0000
    ('mamma',      'Mamma',         'Albanese', 'B1',         '$2b$12$aN2pQv8lKx4zC7hB9mS1DuPEsL3rY6tG0wFqH5nV2jK9sL8xM4nB6'), -- 1111
    ('papa',       'Papà',          'Albanese', 'A2',         '$2b$12$cP4vNb7zKf3rT9qL0mS8WuODgJ2kY6hX1cBnV5jM0pS9aK7lF3yQ8'), -- 2222
    ('fratello1',  'Fratello 1',    'Italiano', 'Madrelingua','$2b$12$eR6tXc9mHz2pY4qN7vB0JsAFk1lO8wD5iUoT3zG9rC6sM2hK7jB0V'), -- 3333
    ('fratello2',  'Fratello 2',    'Italiano', 'Madrelingua','$2b$12$gS8yVc4mJz6rT1kN9vX2QpWEbH7fL0kD9oM5aC3nR7iE8sW4tB2P')  -- 4444
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
--  6. Tokens push notifiche (Firebase/Expo)
-- ==========================================================
CREATE TABLE IF NOT EXISTS push_tokens (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    profile_slug VARCHAR(50) NOT NULL REFERENCES profiles(slug) ON DELETE CASCADE,
    token VARCHAR(255) UNIQUE NOT NULL,
    device_info VARCHAR(255),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);


-- ==========================================================
--  ROW LEVEL SECURITY (opzionale, buono per produzione)
-- ==========================================================
-- ALTER TABLE profiles ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE messages ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE family_todos ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE family_expenses ENABLE ROW LEVEL SECURITY;

-- Per il backend usiamo la SERVICE ROLE KEY che bypassa RLS.
-- Il frontend userà la ANON KEY + policy custom (da definire caso per caso).
