# Security

Please do not publish credentials, session tokens, private invitation links or attendee data in issues. Report suspected vulnerabilities privately to the repository owner through an available private contact channel; GitHub private vulnerability reporting may be used if enabled.

This portfolio application is not a security-audited service. Use a dedicated demo instance for publicly documented demo accounts, never an instance containing real users.

See [security operations](docs/security.md) for controls, secret handling and incident-response guidance, and [deployment](docs/deployment.md) for production configuration. Real deployment secrets must be independently generated and rotated if exposed, including values that previously appeared in Git history.
