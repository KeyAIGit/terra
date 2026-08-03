# TERRA Unreal export validation report

- Status: **VALID**
- Manifest schema: `terra.unreal-import-manifest/v1`
- Run: `terra-life`
- Export digest: `sha256:bf2dfd98e68c822c14a70c654514b3eed8d8668b65461d4039ab2bfba7517c12`
- Content revision digest: `sha256:dfec2bc009b5418c2c748f34745dfbe11b7a83c6d9a79f2a7a9f91f1dfbcd7d3`
- Safe Unreal namespace: `/Game/TerraLife/v_dfec2bc009b5`
- Files covered by digest: 150
- Errors: 0; warnings: 0

## Current export

| Scene | Year | Settlement | Buildings | Roads | People | Scene digest |
|---|---:|---|---:|---:|---:|---|
| `bronze` | -1500 | Nūhā | 108 | 4 | 36 | `sha256:edbcb650fbb84c2b2b94e2ec5c35d6f5340d2139079f3537ed0b3513b75480a5` |
| `capital` | 500 | Raflir | 300 | 11 | 48 | `sha256:d28de9bc176032896c4eb286b93135ddf39619ac389df1200f54f27561d80034` |
| `neolithic` | -6000 | Þūn | 94 | 3 | 28 | `sha256:4a4a9100acadd41cd4229660faa2d876aae2cd32f4ddf75cf06fce6754c51bbc` |

## Entity identity

- Status: **provisional**
- Scheme: `terra.provisional-entity-uuidv5/v1`
- Namespace UUID: `c6e6fa94-b92b-5bae-b40e-62f31a09bdcf`
- Deterministic entity IDs generated: 614
- Stability: Stable only while source index and canonical record are unchanged.
- Migration required: upstream exporter must provide authoritative IDs and an alias map from every provisional UUID.

## Diagnostics

No schema or invariant findings.

## Legacy `/Game/Terra` comparison

| Scene | Legacy map | Legacy building labels | Current buildings | Δ | Legacy NPC labels | Current people | Δ |
|---|---|---:|---:|---:|---:|---:|---:|
| `bronze` | no | — | 108 | — | — | 36 | — |
| `capital` | yes | 302 | 300 | +2 | 48 | 48 | +0 |
| `neolithic` | no | — | 94 | — | — | 28 | — |

Legacy package files inventoried: 71. Counts from `.umap` are recoverable actor-label evidence, not a full Unreal package parse.

## Import safety contract

The importer accepts only `/Game/TerraLife` and the digest-versioned root `/Game/TerraLife/v_dfec2bc009b5`. It refuses `/Game/Terra`, verifies source hashes before any editor mutation, and refuses to overwrite an existing generated scene destination or level.
