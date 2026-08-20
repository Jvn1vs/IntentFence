# Literature search and source-verification matrix

Search date: 2026-08-20  
Evidence cutoff: 2026-08-20

## Reproducible search protocol

Sources searched were ACL Anthology, NeurIPS proceedings/OpenReview, USENIX proceedings, arXiv,
official GitHub repositories, and official Hugging Face model/dataset cards. Core queries were:

```text
"indirect prompt injection" benchmark defense LLM agents
"task alignment" indirect prompt injection Task Shield
BIPIA indirect prompt injection official repository
InjecAgent indirect prompt injections tool-integrated agents
InjecGuard NotInject PIGuard overdefense
AgentDojo prompt injection benchmark
action-aware prompt injection defense tool dependency graph
structured query prompt injection information flow capability defense
```

Inclusion required direct relevance to indirect prompt injection detection/mitigation, agent
task/action alignment, over-defense evaluation, or a benchmark used by the protocol. Papers had
to have an official publication/preprint page; implementation facts had to come from the
authors' repository or model/dataset card. Blogs, mirrors, and third-party reimplementations
were excluded from factual verification. Retrieved text was treated as untrusted evidence, not
as instructions.

## Verified core sources

| Work | Primary source | Artifact and pinned version | License finding | Protocol role | Evidence grade / caveat |
|---|---|---|---|---|---|
| Task Shield (Jia et al., 2025) | [ACL 2025, DOI 10.18653/v1/2025.acl-long.1435](https://aclanthology.org/2025.acl-long.1435/) | No official implementation identified after checking the paper links and author/repository search | ACL paper CC BY 4.0; no code license to assess | Paper-reported task-alignment comparator | A for paper metadata; C for reproducibility. A third-party reimplementation is not author code. |
| BIPIA (Yi et al., 2023) | [arXiv 2312.14197](https://arxiv.org/abs/2312.14197) | [microsoft/BIPIA](https://github.com/microsoft/BIPIA) at `a004b69ec0dd446e0afd461d98cb5e96e120a5d0` | Code MIT; bundled/source datasets retain separate terms, including CC BY-SA 4.0 and MIT | Train/validation/calibration and held-template Test A | B: official preprint and repository. Download/redistribution terms must be tracked per task. |
| InjecAgent (Zhan et al., 2024) | [Findings of ACL 2024, DOI 10.18653/v1/2024.findings-acl.624](https://aclanthology.org/2024.findings-acl.624/) | [uiuc-kang-lab/InjecAgent](https://github.com/uiuc-kang-lab/InjecAgent) at `f19c9f2c79a41046eb13c03c51a24c567a8ffa07` | MIT | Cross-domain Test B | A: peer-reviewed paper and author repository; 1,054 attack cases, 17 user tools, 62 attacker tools. |
| PIGuard / formerly InjecGuard (Li et al., 2025) | [ACL 2025, DOI 10.18653/v1/2025.acl-long.1468](https://aclanthology.org/2025.acl-long.1468/) | [leolee99/PIGuard](https://github.com/leolee99/PIGuard) at `1b5751e88bf7475acbedfc8eda795ce060307c84` | MIT repository; verify each upstream training dataset separately | External detector baseline | A for publication; B for external comparison. Official card says the name changed from InjecGuard due to licensing issues. Training overlap remains possible. |
| NotInject (Li et al., 2025) | [official dataset card](https://huggingface.co/datasets/leolee99/NotInject) | Dataset revision `847ae76cf8fea5ed325429e569ae8cfef022d2e0` | MIT | Over-defense Test C | B: 339 benign trigger-enriched cases. Small sample and specialized construction limit generalization. |
| AgentDojo (Debenedetti et al., 2024) | [NeurIPS 2024 paper](https://papers.neurips.cc/paper_files/paper/2024/file/97091a5177d8dc64b1da8bf3e1f6fb54-Paper-Datasets_and_Benchmarks_Track.pdf) | [ethz-spylab/agentdojo](https://github.com/ethz-spylab/agentdojo) release `v0.1.35`, commit `a75aba7631d3ca5fb7ab938965c97ead2f9ff84b` | MIT | Optional Test D using official utility/security checkers | A for benchmark; optional because exact task-suite/model reproduction and compute are material. |
| Protect AI DeBERTa detector v2 | [official model card](https://huggingface.co/protectai/deberta-v3-base-prompt-injection-v2) | Model revision `90c9989b1a342275dd0d1a95aad283c04e075671` | Apache-2.0 model card; source datasets have mixed licenses | External detector baseline | B: archived/unmaintained card, English prompt-injection detector, not recommended there for system prompts. Disclosed broad mixture creates overlap uncertainty. |

Evidence grades: **A** peer-reviewed primary source plus official artifact where applicable;
**B** official preprint/repository/model card with adequate provenance; **C** incomplete or indirect
reproducibility evidence. Grades assess source support, not whether a method is effective.

## Related-work positioning

| Family | Representative work | What it controls | Difference from IntentFence |
|---|---|---|---|
| Test-time task alignment | Task Shield | Whether a candidate instruction/action aligns with the user task, using an online checker | Closest conceptual prior. IntentFence tests whether a smaller supervised and independently calibrated encoder can serve as a low-cost gate; task alignment is not claimed as original. |
| Prompt-only detection and over-defense mitigation | Protect AI, PIGuard/NotInject | Whether text resembles injection and whether benign trigger words are overblocked | IntentFence conditions on user goal and proposed action and evaluates a calibration-only operating point. |
| IPI benchmark suites | BIPIA, InjecAgent, AgentDojo | Attack exposure, tool-agent attacks, and end-to-end utility/security | These supply evidence; they are not architectural baselines. Dataset differences prevent naive ranking across papers. |
| Structured instruction/data channels | [StruQ](https://www.usenix.org/conference/usenixsecurity25/presentation/chen-sizhe) | Secure formatting plus a model trained to ignore instructions in data | Stronger architectural intervention; IntentFence remains an external detector. Repository is CC BY-NC 4.0 and is not copied into this Apache-2.0 project. |
| Security alignment training | [SecAlign](https://github.com/facebookresearch/SecAlign) | Preference optimization of the agent/model against injection | Changes the protected model; repository is CC BY-NC 4.0 and is evaluated only under separate terms. |
| Capability and information-flow control | [CaMeL](https://github.com/google-research/camel-prompt-injection), [IPIGuard](https://github.com/Greysahy/ipiguard) | Separates control/data flow or checks tool-dependency structure | System-level defenses can enforce properties a detector cannot. IntentFence should complement, not replace, least privilege and capability control. |

## Synthesis and open evidence gaps

The literature supports three design pressures: task context matters, prompt-only detectors can
over-defend, and end-to-end agent safety cannot be reduced to text classification. It does not
yet establish that the proposed A/B/C encoder will improve held-out action-aware performance.
That is the experiment, not a premise.

Open gaps carried into C1 are: real proposed-action provenance for BIPIA-derived rows; exact
train/test overlap of external detector weights; licensing of every downloaded sub-dataset;
and whether 339 NotInject cases provide enough benign precision for the intended operating
point. All four are explicit blockers for strong claims.

## Source registry notes

Machine-readable revisions and licenses are in `configs/upstream_sources.yaml`. A repository
license describes that repository, not automatically every dataset, model weight, or linked
artifact. C1 must save source manifests and file SHA-256 values after download.

