# Route B v2 candidate 4 data card

Status: `STRUCTURE_VALIDATED_HUMAN_AUDIT_PENDING_NOT_TRAINING_AUTHORIZED`

Prepared: 2026-08-24
Source: project-owned offline mock-tool scenarios only

## Scope and licensing

The project owner approved the Route B 2.0 direction and construction of a project-owned
offline mock-tool corpus. BIPIA Table/Code and all other not-separately-approved CC BY-SA or
noncommercial external data remain excluded. InjecAgent, NotInject, and AgentDojo remain
evaluation-only and contributed no candidate 4 training rows.

## Candidate counts

| Role | Rows | Base cases | Template groups | Per Risk class | Per Alignment class |
|---|---:|---:|---:|---:|---:|
| train | 5,000 | 250 | 50 | 1,000 | 1,250 |
| validation | 2,000 | 100 | 20 | 400 | 500 |
| calibration | 10,000 | 500 | 100 | 2,000 | 2,500 |
| Test A2 | 10,000 | 500 | 100 | 2,000 | 2,500 |
| **Total** | **27,000** | **1,350** | **270** | **5,400** | **6,750** |

Every base case has a complete `5 Risk × 4 task Alignment` counterfactual matrix. The
observed Risk/Alignment mutual information is exactly 0 bits by construction; this is a
controlled independence design, not an empirical population claim.

Calibration and Test A2 each contain 2,000 benign rows. At a planning point of 1% FPR, one
error is 0.05 percentage points and the nominal row-level 95% Wilson half-width is about
0.446 percentage points. Cluster-aware uncertainty remains mandatory.

## Action evidence

- Action provenance: `sandbox_policy_output` for all 27,000 rows.
- Captured action traces: 27,000.
- Executed actions: 0.
- External side effects: 0.
- Every action has an observation ID, policy ID, and parameter-level field provenance.

The mock action vocabulary covers messaging, calendar, files, tickets, storage, reporting
databases, permission management, invoices, directories, and project workspaces. All people,
addresses, files, resources, and identifiers are synthetic; email domains use `.test`.

## Integrity evidence

- Manifest sealed SHA-256: `42f9f0f29d75fd62148c4373eb83f3ad23e863dd74c65e8cebcc13d59a194c7b`.
- Duplicate sample IDs: 0.
- Exact content duplicates across roles: 0.
- Template groups crossing roles: 0.
- Normalized action signatures crossing roles: 0.
- Template representatives checked at Jaccard threshold 0.92: 5,400.
- Candidate/comparison pairs: 69,452.
- Detected cross-role near duplicates: 0.

Candidate 1 was rejected for two wildcard ticket action signatures that crossed roles.
Candidate 2 removed that defect but still exposed role-coded entity prefixes. Candidate 3
removed those prefixes and passed structural checks; candidate 4 superseded it by sealing
the generator and runtime source hashes in the manifest. Rejected/superseded data remain
ignored local evidence and are not committed.

## Human audit

Two independently ordered, seed-label-blinded packages were generated. Each of two distinct
human reviewers must independently label the same 400 Risk items and 400 Alignment/action
items. Seed labels remain sealed until both submissions are complete. Pre-registered gates
cover completion, raw agreement, Cohen's kappa, per-seed-class agreement, and action realism.

- Audit manifest sealed SHA-256: `05eaf499f3666f096a4a2f9a189e40da95b96e8fd37ff4f6f012896f6049e612`.
- Sealed seed-label file SHA-256: `acd1847b48f831c6dd8f146865279c845ecd246eae9580617d66a3cc7031fa42`.
- Reviewer sheets expose no seed labels; the analyzer verifies the manifest, sealed labels,
  immutable question content, reviewer identity separation, and completion metadata.

No human review has been completed yet. Therefore `human_verified=0` for candidate 4,
protocol 2.0.0 remains unfrozen, and `formal_training_authorized=false`. No learned baseline,
model weight, temperature, or threshold was fitted.
