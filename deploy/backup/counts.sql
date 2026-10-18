-- Row count of every table in the public schema as one JSON object, e.g. {"activities": 812, ...}.
-- Run inside the backup's snapshot at backup time (written next to the dump as .counts.json) and
-- against the scratch database after a restore; restore-check compares the two (ADR 0024).
SELECT coalesce(json_object_agg(table_name, n ORDER BY table_name), '{}'::json)
FROM (
    SELECT table_name::text,
           (xpath('/row/n/text()',
                  query_to_xml(format('SELECT count(*) AS n FROM %I.%I', table_schema, table_name),
                               false, true, '')))[1]::text::bigint AS n
    FROM information_schema.tables
    WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
) AS counts;
