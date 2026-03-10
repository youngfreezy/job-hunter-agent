-- Create separate database for Skyvern service
SELECT 'CREATE DATABASE skyvern'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'skyvern')\gexec
