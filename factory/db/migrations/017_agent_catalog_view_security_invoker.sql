-- Apply the caller's permissions and RLS policies when reading the catalog view.
ALTER VIEW agent_catalog_read SET (security_invoker = true);
