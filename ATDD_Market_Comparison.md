# ATDD Market Comparison and Non-Reinvention Analysis

**Working draft**  
**Purpose:** Compare ATDD with adjacent market categories and clarify where ATDD should integrate instead of competing.

---

## 1. Executive verdict

ATDD does not appear to be a direct reinvention of a single existing product category.

The market already has many strong pieces:

- agent frameworks;
- agent/tool interoperability protocols;
- policy-as-code engines;
- static analyzers;
- CI/CD systems;
- supply-chain integrity frameworks;
- developer portals;
- test frameworks.

But these tools do not usually define a complete software delivery protocol that binds together:

```txt
conventions
scopes
gates
extensions
workspace providers
implementations
violations
evidence
agent/human/CI execution loops
```

That is the ATDD opportunity.

The risk is not that ATDD duplicates one product. The risk is that ATDD accidentally tries to become all of them.

The discipline should be:

> ATDD should be the contract layer, not the execution engine for every category.

---

## 2. Comparison table

| Category | Examples | What they already solve | Where ATDD overlaps | Where ATDD should differ |
|---|---|---|---|---|
| Agent frameworks | OpenAI Agents SDK, Microsoft Agent Framework / AutoGen, CrewAI | Build and orchestrate agents, tools, handoffs, memory, sessions, workflows | Agents may execute ATDD tasks or respond to ATDD violations | ATDD should not be an agent framework. It should define the delivery contract agents follow. |
| Agent/tool protocols | MCP, A2A-style protocols | Tool discovery, tool invocation, agent communication | ATDD capabilities can be exposed as tools or agent messages | ATDD should not replace tool/agent protocols. It should define software delivery semantics carried through them. |
| Policy-as-code | OPA/Rego, Conftest, Kyverno | Declarative policy decisions and enforcement | ATDD conventions may be enforced by policy engines | ATDD should not invent a general policy language. It should map policies to delivery conventions, gates, and evidence. |
| Static analysis / code scanning | Semgrep, CodeQL, ESLint, Ruff, mypy | Detect code findings, style issues, security issues, type errors | ATDD implementations may wrap or normalize scanner outputs | ATDD should not become a scanner. It should normalize violations and tie them to delivery rule IDs. |
| Test frameworks | pytest, Vitest, Jest, Go test, Cargo test | Execute tests in language ecosystems | ATDD workspace providers may define how these runtimes execute implementations | ATDD should not replace test runners. It should standardize how test-backed implementations map to conventions and evidence. |
| CI/CD systems | GitHub Actions, GitLab CI, Buildkite, Dagger, Tekton, Argo | Run workflows, jobs, builds, tests, deployments | ATDD gates can run in CI/CD systems | ATDD should not become CI. It should define what must run, when, and what output means. |
| CD event standards | CDEvents | Standardize continuous delivery event data for interoperability | ATDD evidence can map into delivery events | ATDD should not replace CD events. It should generate delivery evidence that can be emitted through event standards. |
| Supply-chain integrity | SLSA, in-toto, Sigstore, SBOM tooling | Provenance, artifact integrity, tamper resistance, supply-chain verification | ATDD evidence can feed attestations and provenance | ATDD should not replace supply-chain frameworks. It should provide higher-level delivery-rule evidence. |
| Developer portals / golden paths | Backstage | Catalog software, scaffold templates, unify developer tooling | ATDD extensions can encode golden path rules and delivery conventions | ATDD should not become the portal. It should provide enforceable delivery contracts behind the portal. |

---

## 3. Agent frameworks

### What exists

Agent frameworks focus on creating and orchestrating AI agents.

Examples include:

- OpenAI Agents SDK;
- Microsoft Agent Framework / AutoGen lineage;
- CrewAI.

OpenAI describes agents as applications that plan, call tools, collaborate across specialists, and keep state for multi-step work.[^openai-agents] Microsoft describes its Agent Framework as a successor combining AutoGen-style abstractions for single- and multi-agent patterns with enterprise features such as state management, type safety, telemetry, and model support.[^ms-agent-framework] CrewAI positions itself around production-ready multi-agent systems, crews, flows, guardrails, memory, knowledge, and observability.[^crewai]

### Overlap with ATDD

Agents can be actors inside ATDD.

An agent might:

- inspect conventions;
- run gates;
- fix violations;
- ask another agent to repair a failing implementation;
- produce evidence for a delivery step.

### Difference

Agent frameworks ask:

```txt
How do we create, coordinate, and run agents?
```

ATDD asks:

```txt
What software delivery contract must any actor satisfy?
```

ATDD should not compete with agent frameworks.

ATDD should define the protocol that agents follow.

---

## 4. Agent/tool interoperability protocols

### What exists

MCP standardizes how LLM applications integrate with external data sources and tools, and its tool specification allows servers to expose named tools with schemas that models can invoke.[^mcp-spec][^mcp-tools]

### Overlap with ATDD

ATDD could expose capabilities through MCP-style tools:

```txt
atdd.list_conventions
atdd.resolve_gate
atdd.validate
atdd.explain_violation
atdd.apply_fix
atdd.emit_evidence
```

### Difference

MCP answers:

```txt
How does a model discover and call tools?
```

ATDD answers:

```txt
What does correct software delivery mean, and how is that checked?
```

MCP can carry ATDD operations. It does not define ATDD’s delivery semantics.

---

## 5. Policy-as-code

### What exists

OPA is a general-purpose policy engine that provides a declarative language and APIs to offload policy decision-making from software systems.[^opa-docs]

Policy-as-code is mature and should not be reinvented.

### Overlap with ATDD

Some ATDD conventions can be implemented by policy engines.

Example:

```txt
ATDD convention:
  container image must not run as root

Possible implementation:
  OPA/Rego policy
```

### Difference

OPA answers:

```txt
Given this input, does this policy allow or deny it?
```

ATDD answers:

```txt
Which convention owns this rule?
Where does it apply?
Which gate enforces it?
Which implementation executes it?
Which violation maps back to which rule_id?
What evidence proves the gate ran?
```

ATDD should integrate policy engines as implementation backends, not replace them.

---

## 6. Static analysis and code scanning

### What exists

Semgrep is a static analysis tool that searches code, finds bugs, and enforces secure guardrails and coding standards; it supports many languages and can run in IDE, pre-commit, and CI/CD workflows.[^semgrep-github]

Other tools in this category include CodeQL, ESLint, Ruff, mypy, and language-specific linters.

### Overlap with ATDD

ATDD implementations may wrap scanners.

Example:

```txt
ATDD convention:
  source files must declare a component header

Possible implementations:
  custom pytest validator
  Semgrep rule
  AST parser
  language server rule
```

### Difference

Scanners produce findings.

ATDD should normalize those findings into delivery violations:

```txt
Violation(
  rule_id="coder.source.component-header-required",
  file="src/foo.py",
  line=12,
  severity="error",
  gate="pre-push"
)
```

The scanner can vary. The delivery contract should not.

---

## 7. Test frameworks and workspace providers

### What exists

Language ecosystems already have mature test runners:

```txt
pytest
Vitest
Jest
Go test
Cargo test
```

### Overlap with ATDD

ATDD workspace providers can standardize how implementations run on those runtimes.

Example:

```txt
atdd.workspace.python-pytest
  owns pytest runtime contract
  owns test discovery behavior
  owns command shape
  owns shared runtime files
```

### Difference

pytest answers:

```txt
How do I run Python tests?
```

ATDD answers:

```txt
Which delivery convention does this test-backed implementation enforce?
Which rule_id does a failure map to?
Which gate does this affect?
What evidence should be emitted?
```

Workspace providers should be first-class in ATDD because common runtimes are shared by default.

---

## 8. CI/CD systems

### What exists

GitHub Actions is a CI/CD platform for automating build, test, and deployment pipelines.[^github-actions] Dagger positions itself as a way to build, test, and deploy codebases repeatably, running locally, in CI, or in the cloud.[^dagger]

### Overlap with ATDD

ATDD gates can run inside CI/CD systems.

Example:

```yaml
- name: ATDD CI Gate
  run: atdd validate --gate ci
```

### Difference

CI/CD answers:

```txt
How do I run jobs?
```

ATDD answers:

```txt
What delivery contract must this job enforce?
What conventions apply?
What violations block the gate?
What evidence is produced?
```

ATDD should not be a CI engine.

ATDD should be portable across CI engines.

---

## 9. Continuous delivery event standards

### What exists

CDEvents is a common specification for Continuous Delivery events intended to enable interoperability across the software production ecosystem.[^cdevents]

### Overlap with ATDD

ATDD evidence could be emitted as or attached to continuous delivery events.

Example:

```txt
ATDD gate result → CDEvents-compatible event
```

### Difference

CDEvents standardizes event shapes.

ATDD should define what delivery semantics produced the event.

---

## 10. Supply-chain integrity

### What exists

SLSA is a software supply-chain security framework with standards and controls to prevent tampering, improve integrity, and secure packages and infrastructure.[^slsa]

in-toto protects software supply-chain integrity by verifying that expected tasks were performed as planned, by authorized actors, and that products were not tampered with in transit.[^intoto-github]

### Overlap with ATDD

ATDD evidence can feed provenance and attestation systems.

Example:

```txt
ATDD evidence:
  convention_set: v1.4.0
  workspace_provider: atdd.workspace.python-pytest@1.0.0
  implementation: component-header-validator@1.2.0
  gate: ci
  result: pass
  artifact_digest: sha256:...
```

### Difference

Supply-chain frameworks focus on integrity, provenance, authorization, and tamper resistance.

ATDD focuses on delivery conventions, gate semantics, violations, and executable feedback loops.

ATDD should feed supply-chain systems, not replace them.

---

## 11. Developer portals and golden paths

### What exists

Backstage is an open source developer portal framework that centralizes software catalogs, infrastructure tools, and developer workflows.[^backstage]

### Overlap with ATDD

Backstage can scaffold repositories and expose golden paths. ATDD can encode the enforceable delivery contract behind those golden paths.

Example:

```txt
Backstage template creates service repo
ATDD extension declares delivery conventions
ATDD validators enforce them
CI emits ATDD evidence
```

### Difference

Backstage answers:

```txt
How do developers discover, scaffold, and operate software through a portal?
```

ATDD answers:

```txt
What machine-readable delivery rules must this software satisfy?
```

---

## 12. The ATDD gap

The market has engines.

ATDD should be the protocol that coordinates them.

Existing tools are strong at:

```txt
running agents
calling tools
scanning code
running policies
executing CI jobs
building artifacts
emitting supply-chain attestations
scaffolding developer workflows
```

ATDD’s gap is:

```txt
standardizing software delivery expectations as explicit, executable, agent-readable contracts
```

That includes:

```txt
what rules exist
where they apply
when they run
what executes them
how violations are shaped
how evidence is produced
how agents/humans/CI systems close the loop
```

---

## 13. Reinvention boundaries

ATDD should not build the following unless absolutely necessary:

| Do not reinvent | Use instead |
|---|---|
| General policy language | OPA/Rego or existing policy engines |
| Static analysis engine | Semgrep, CodeQL, linters, custom adapters |
| CI engine | GitHub Actions, GitLab CI, Dagger, Buildkite, Tekton, Argo |
| Agent orchestration framework | OpenAI Agents SDK, Microsoft Agent Framework, CrewAI, LangGraph-style systems |
| Tool invocation protocol | MCP or similar protocols |
| Supply-chain attestation framework | SLSA, in-toto, Sigstore, SBOM/provenance tooling |
| Developer portal | Backstage or similar portals |

ATDD should define adapters and contracts around these tools.

---

## 14. What ATDD should own directly

ATDD should own the protocol spine:

```txt
Extension
Convention
Scope
Gate
Workspace Provider
Workspace Instance
Implementation
Violation
Evidence
```

This spine is the part that no adjacent tool cleanly owns for agentic software delivery.

---

## 15. Over-engineering risks

ATDD becomes over-engineered if it tries to become a platform too early.

Avoid building:

- a remote marketplace before local resolution works;
- a complex semantic version solver before exact versions work;
- a custom policy language before adapters are exhausted;
- a custom static analysis engine before wrappers are proven insufficient;
- a full CI runtime before existing CI integration is stable;
- a custom agent protocol before MCP/A2A-style integration is tested;
- a full supply-chain attestation system before ATDD evidence has a stable shape.

The right sequence is:

```txt
1. Define the protocol spine.
2. Define violation and evidence formats.
3. Define first-class workspace providers.
4. Provide a small official provider set.
5. Integrate with existing tools through adapters.
6. Add ecosystem machinery only when usage forces it.
```

---

## 16. Strategic positioning

The clearest market position is:

> ATDD is a software delivery protocol for humans, agents, and automation.

It is not trying to make agents smarter.

It is trying to make delivery more deterministic.

It makes project conventions explicit, executable, and portable across actors.

That is why ATDD can coexist with agent frameworks, CI/CD systems, policy engines, static analyzers, and supply-chain frameworks.

ATDD is not the engine.

ATDD is the delivery contract those engines can execute.

---

## References

[^openai-agents]: OpenAI, “Agents SDK,” https://developers.openai.com/api/docs/guides/agents
[^ms-agent-framework]: Microsoft, “Microsoft Agent Framework Overview,” https://learn.microsoft.com/en-us/agent-framework/overview/
[^crewai]: CrewAI, “CrewAI Documentation,” https://docs.crewai.com/
[^mcp-spec]: Model Context Protocol, “Specification,” https://modelcontextprotocol.io/specification/2025-06-18
[^mcp-tools]: Model Context Protocol, “Tools,” https://modelcontextprotocol.io/specification/draft/server/tools
[^opa-docs]: Open Policy Agent, “OPA Documentation,” https://openpolicyagent.org/docs
[^semgrep-github]: Semgrep GitHub repository, https://github.com/semgrep/semgrep
[^github-actions]: GitHub Docs, “Understanding GitHub Actions,” https://docs.github.com/articles/getting-started-with-github-actions
[^dagger]: Dagger, “A better way to ship,” https://dagger.io/
[^cdevents]: CDEvents, “CDEvents,” https://cdevents.dev/
[^slsa]: SLSA, “Supply-chain Levels for Software Artifacts,” https://slsa.dev/
[^intoto-github]: in-toto GitHub repository, https://github.com/in-toto/in-toto
[^backstage]: Backstage, “Software Catalog and Developer Platform,” https://backstage.io/
