# AI-use disclosure and responsibility statement

Status: draft template for the eventual paper/repository release. It is not a substitute for a
venue-specific policy check or project-owner approval.

## Current project record

AI assistance was used to help implement and review software structure, write tests and
documentation, organize reproducibility checks, and perform the project-authorized data-workflow
engineering tasks recorded in the repository. AI-generated review outputs are labeled as
`ai_reviewed_engineering_only`; they are not independent human label review and do not set
`human_verified=true`, authorize training, authorize calibration, or unlock formal final testing.

The project owner remains responsible for independent human review, protocol amendments, model
training, learned-parameter fitting, final-test authorization, interpretation of results and the
decision to publish. Demonstrations and tests use rules, mocks or offline fixtures; they do not
send, upload, delete, pay or change permissions in real systems.

## External-service record

For each future run, record whether an external model/API received any project material:

| Run or artifact | Provider/model | Material class sent | Consent/terms | Retention or deletion | Evidence |
|---|---|---|---|---|---|
| `[fill per run]` | `[fill]` | `[none / synthetic fixture / approved excerpt]` | `[fill]` | `[fill]` | `[manifest or log]` |

Do not infer “no external transmission” from an empty row. Fill `none` explicitly after checking
the run environment. Never send raw third-party data, private notes, credentials or unpublished
manuscripts merely because a provider key is configured.

## Paper disclosure template

> During software development and manuscript preparation, the authors used AI-assisted tools for
> code scaffolding, test design, documentation editing and language assistance. The authors
> reviewed the resulting materials, remain responsible for all claims and analyses, and did not
> delegate independent human label verification, learned-parameter fitting, final-test
> authorization or publication decisions to an AI system.

Adapt this paragraph to the target venue's current policy. If external model calls or AI-generated
content are used in a future experiment, identify the provider, model/revision, material class,
purpose, consent/terms and retention policy rather than hiding them under a generic statement.

## Authorship, funding and conflicts

- Author Contributions (CRediT): `[fill after the project owner confirms roles]`.
- Funding: `[fill actual funding or state no external funding after confirmation]`.
- Conflicts of interest: `[fill after author review]`.
- Ethics/data statement: use the project threat model and source-license records; do not claim
  human-subject approval when no such study was conducted.
