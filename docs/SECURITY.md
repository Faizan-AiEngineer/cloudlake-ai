# Security and trust model

CloudLake AI binds local services to loopback and assumes one trusted workspace owner. A public or shared deployment requires authentication, authorization, a private operational network, hardened service accounts and independent security review.

The API restricts CORS to the configured UI origin. Request bodies, preview lengths, filenames and dataset names are bounded. Uploads use service-generated prefixes and atomic file placement. The analytical layer exposes fixed queries with parameterized filters, restricted DuckDB filesystem access and an interrupt timeout. CSV and spreadsheet exports escape formula-looking text. System endpoints omit credentials.

Pipeline code serializes workspace writes under an OS file lock. It writes immutable snapshots before atomically advancing the pointer and manifests. A blocked rule leaves existing publication metadata intact. Local account access to files and runtime environment is trusted. The service does not implement multi-tenant isolation, user audit identities, or TLS termination.

AWS configuration limits routine Lambda access to the designated Glue job and queue and scope-limits Glue to the lake and catalog. The public access block and TLS-only bucket policy protect S3. Provider permission and integration behavior require a reviewed deployment.
