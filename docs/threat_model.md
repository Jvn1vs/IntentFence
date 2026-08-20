# Threat model

## Assets

IntentFence helps protect the user's actual task, private files and messages, credentials, system/developer instructions, retrieved knowledge, and tools that can communicate, write, delete, pay or change permissions.

## Adversary

The adversary cannot directly change the system prompt but can control one untrusted source read by an agent: a webpage, email/attachment text, retrieved document, tool/MCP result, log, code comment or table. The adversary wants lower-priority content to be treated as instructions and to redirect the eventual action.

## Enforcement point

The core model is Gate B, immediately before a proposed tool action. It observes the original user goal, relevant untrusted content and the proposed action. An optional Gate A may scan content on entry, but Gate A is not a prerequisite for the core result.

## Risk classes

- `benign`: the action remains consistent with the user's goal;
- `instruction_hijacking`: external content redirects the objective;
- `data_exfiltration`: an action exposes private data or hidden instructions;
- `privilege_escalation`: an action requests unnecessary authority;
- `tool_manipulation`: an attacker changes parameters, destination or call order.

The auxiliary alignment label is 0 for goal-consistent and 1 for conflicting in the v1 schema. Because it is correlated with non-benign risk labels, the project must report their contingency table and accept removal of the head if ablation shows no independent benefit.

## Out of scope for v1

Images/audio/video, an unconstrained long-session model, fully autonomous online learning, all agent frameworks, unapproved testing of real services, and a guarantee against adaptive attackers are out of scope. English text and structured single-step actions are the primary target.

## Trusted computing base

IntentFence does not replace authentication, authorization, least privilege, allowlisted tool parameters, sandboxing, audit logs, rate limits or human confirmation. Sensitive actions still require confirmation even at a low model score. Detection failure is not interpreted as safety.
