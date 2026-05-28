# DevOps profile

The `devops.toml` profile in this public mirror is a thin public-safe subset. It ships:

- `observability/ha-alert-triage` and `observability/market-audit-deployed-stack` for ops-side observability work.
- `meta/agents-md-curator`, `meta/playbook-promote`, `meta/playbook-retrospective` for lifecycle.
- `productivity/handoff` for end-of-session handoff documents.

Plus the always-on rules (`writing-style`, `no-em-dashes`, `no-ticket-ids-in-code`, `never-push-to-develop`), the `never-push-to-develop` and `agent-memory-session-brief` hooks, and the `slack` MCP.

The workplace-specific DevOps skills (cloud secrets manager workflows, error-tracker issue triage, internal k8s dashboard verification, vendor-specific CI pipeline debugging) are designed in the upstream and intentionally not shipped in this public mirror. The downstream profile stays thin because the workflows these skills encode are too workplace-shaped to be portable to a generic open-source mirror.

## External skills to install separately

For project-specific DevOps work, the right pattern is to layer in external skill collections published by the tool vendors themselves.

### Terraform + Packer (HashiCorp official)

Source: [hashicorp/agent-skills](https://github.com/hashicorp/agent-skills) (MPL-2.0). Published by the company that maintains the tooling, so the skill semantics track upstream changes accurately.

Install per project (when the project actually uses Terraform):

```bash
npx skills add hashicorp/terraform
npx skills add hashicorp/packer
```

### Generic K8s helpers

The `derisk-ai/awesome-devops-skills` catalog lists generic Kubernetes skills maintained by various authors. Quality varies; inspect the SKILL.md before installing and verify the maintainer + license.

### Cloud provider CLIs

AWS, Azure, GCP each have their own agent-skill collections. Pick a cloud-specific skill set that matches the project's primary cloud.

## Composing with other roles

A DevOps engineer who also writes backend code can install both profiles:

```bash
make install PROFILE=devops,backend-developer
```

The installer unions the skill / rule / hook / MCP lists and dedupes.
