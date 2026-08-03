# Security policy

## Secrets

Never commit API keys, GitHub/Hugging Face tokens, Unreal service credentials,
private handoff files, or browser-side production keys. Use macOS Keychain or
local environment variables for development and repository/CI secret storage
for automation. Hugging Face Datasets, including private datasets, are not a
secret manager.

Any credential that has appeared in a handoff, prompt, terminal output, log, or
generated artifact must be treated as compromised and rotated. Encoding a token
with base64 does not protect it.

## Runtime boundaries

- A packaged Unreal client must not contain permanent model or database secrets.
- Unreal MCP is editor-only and must bind to localhost.
- External AI calls require an authenticated server-side boundary, allowlists,
  budgets, redaction, and an offline fallback.
- Raw user voice/video and biometric character references require consent,
  retention rules, and access controls.
- Licensed datasets and assets must pass provenance and distribution checks
  before they enter a public build.

## Reporting

Use a private GitHub security advisory for vulnerabilities or credential
exposure. Do not open a public issue containing secrets or personal data.
