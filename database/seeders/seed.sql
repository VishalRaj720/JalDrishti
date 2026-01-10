-- Seed data for 1st Month Project - Users Entity Only
-- Run this after database is created and migrations are applied

-- Insert default admin user
-- Password: admin123 (hashed with bcrypt)
INSERT INTO users (id, email, password_hash, name, role, created_at, updated_at)
VALUES (
  gen_random_uuid(),
  'admin@example.com',
  '$2b$10$O.XYcueT05F78S1zs/BGNV1WuEZr6ffwdQkneb7YUlSw1s', -- admin123
  'Admin User',
  'admin',
  NOW(),
  NOW()
) ON CONFLICT (email) DO NOTHING;

-- Insert analyst user
-- Password: analyst123 (hashed with bcrypt)
INSERT INTO users (id, email, password_hash, name, role, created_at, updated_at)
VALUES (
  gen_random_uuid(),
  'analyst@example.com',
  '$2b$10$vmV8aHxjzgr/pZmSC1rMP.33L8gvms4ds1XUviZeJfyR7KI9/bcGIe', -- analyst123
  'Analyst User',
  'analyst',
  NOW(),
  NOW()
) ON CONFLICT (email) DO NOTHING;

-- Insert viewer user
-- Password: viewer123 (hashed with bcrypt)
INSERT INTO users (id, email, password_hash, name, role, created_at, updated_at)
VALUES (
  gen_random_uuid(),
  'viewer@example.com',
  '$2b$10$O.XYcueT05F78S1zs/BGNV1WuEZr6ffwdQkneb7YUlSw1s', -- viewer123 (same hash for now)
  'Viewer User',
  'viewer',
  NOW(),
  NOW()
) ON CONFLICT (email) DO NOTHING;
