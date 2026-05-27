# DevOps profile

The `devops.toml` profile bundles 4 native skills tuned to team's actual DevOps surface (AWS Secrets Manager, error-tracking, the k8s cluster, CI) plus the AGENTS.md curator and a few cross-role helpers.

DevOps tooling that lives outside team (Terraform, Packer, generic Kubernetes helpers) is NOT vendored into this profile. The playbook's import-strategy lock decided "team-native + external reference" for DevOps because:

- The `derisk-ai/awesome-devops-skills` catalog is a metalist of other repos, not a direct skill source.
- HashiCorp ships an official `hashicorp/agent-skills` collection covering Terraform + Packer that you can install on a per-project basis.
- team's DevOps surface is org-specific enough that the 6-8 high-leverage moves are not in any upstream skill repo.

## External skills to install separately

When you need Terraform / Packer / generic K8s skill coverage on a project, install upstream skills via the agent's own skill-add mechanism. The list below is curated, not exhaustive; pick what fits the project.

### Terraform + Packer (HashiCorp official)

Source: [hashicorp/agent-skills](https://github.com/hashicorp/agent-skills) (MPL-2.0). Published by the company that maintains the tooling, so the skill semantics track upstream changes accurately. Treat this collection as the canonical entry point when a project pulls in Terraform or Packer.

Install per project (when the project actually uses Terraform):

```bash
npx skills add hashicorp/terraform
npx skills add hashicorp/packer
```

The HashiCorp skills cover code generation, plan analysis, state inspection, and module authoring. They do not duplicate any team-native DevOps skill in this profile.

### Generic K8s helpers (Helm, K9s, Kompose)

The `derisk-ai/awesome-devops-skills` catalog lists generic Kubernetes skills maintained by various authors. Quality varies; treat each as a candidate, not a guarantee. Inspect the SKILL.md before installing; verify the maintainer + license.

The team-native `devops/k8s-dashboard-verify` skill is the canonical entry point for team's cluster work. Generic K8s skills supplement that for project-specific tasks (Helm chart authoring, K9s navigation patterns), they do not replace it.

### Cloud provider CLIs

AWS, Azure, GCP each have their own agent-skill collections. team is AWS-primary (Secrets Manager, EKS, S3) so an AWS-focused skill set is the highest leverage:

- [`awslabs/aws-agent-skills`](https://github.com/awslabs): search for current AWS agent skill collections; AWS publishes several under different sub-orgs.

The team-native `devops/aws-secrets-configmap-apply` skill covers the specific Secrets Manager configmap path the AI Backend + MCP read from. Generic AWS skills supplement that for broader AWS work (IAM, S3, cost analysis).

## Why this profile is intentionally thin

The 4 native skills cover the four highest-frequency DevOps moves at team:

1. Configmap apply (rotating model deployment names, env-driven config).
2. error-tracking triage (production error analysis before paging on-call).
3. K8s dashboard verify ("is X live yet").
4. CI pipeline debug (post-merge or deploy-time pipeline failures).

Adding a fifth and sixth native skill (`redis-sidecar-debug`, `bedrock-marketplace-iam`) is straightforward when the recurring need shows up. The playbook's promotion path (`/playbook-retrospective` then `/playbook-promote`) is the right way to graduate the next ones.

For DevOps engineers wearing multiple hats (e.g. DevOps + backend), install both profiles together:

```bash
make install PROFILE=devops,backend-developer
```

(or, equivalently, `python3 scripts/install.py --profile devops,backend-developer`)

The installer unions the skill / rule / hook / MCP lists and dedupes.
