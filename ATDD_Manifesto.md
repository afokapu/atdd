# ATDD Manifesto

**Working draft**  
**Purpose:** Position ATDD as a software delivery protocol for agentic and human software work.

---

## 1. The thesis

**ATDD does not make agents smarter. ATDD makes software delivery more deterministic.**

The market is racing toward smarter agents: better reasoning, larger context, stronger planning, better tool use, more autonomy. That is useful, but it is not enough.

Software delivery should not depend on whether the current agent is brilliant, lucky, or context-rich enough to infer every hidden convention of a project.

ATDD starts from a different premise:

> Do not trust the agent's cognition. Trust the delivery system.

ATDD defines the protocol by which software work becomes explicit, checkable, repeatable, and deliverable.

---

## 2. The problem

Modern software delivery still depends on too much invisible human cognition.

Humans know the unwritten rules:

- where files should go;
- what naming conventions mean;
- which architectural boundaries matter;
- which tests are expected;
- what “done” really means;
- which changes are safe;
- which delivery gates must pass;
- when a change is incomplete even if the code compiles.

Agents do not reliably know those things unless they are encoded somewhere.

When those rules live in someone’s head, an agent must guess. When an agent guesses, delivery quality depends on model intelligence. That is fragile.

ATDD exists to move delivery knowledge out of human memory and into a machine-readable delivery protocol.

---

## 3. The core idea

**Less trust in cognition. More trust in executable conventions.**

ATDD turns software delivery into a closed loop:

```txt
Convention → Scope → Gate → Workspace Provider → Implementation → Violation/Evidence
```

The agent, human, or CI system does not need to infer the delivery contract from vibes.

It can ask:

```txt
What conventions apply?
Where do they apply?
When must they run?
What executes them?
What result shape is expected?
What violation points back to which rule?
What evidence proves the gate passed?
```

That is the protocol layer ATDD wants to standardize.

---

## 4. Strong positioning statements

### ATDD is a protocol, not a platform.

ATDD should not become a replacement for CI engines, policy engines, static analyzers, agent frameworks, developer portals, or supply-chain systems.

ATDD should define the delivery contract that those tools can execute, enforce, observe, or report.

### ATDD is contracts, not vibes.

A delivery rule should not be a vague instruction like:

```txt
Make sure this follows our architecture.
```

It should become:

```txt
rule_id: coder.source.component-header-required
scope: source files matching X
gate: pre-push, ci
validator: component-header implementation
output: Violation(rule_id=..., file=..., line=..., severity=...)
```

### ATDD is evidence, not confidence.

An agent saying “I think this is done” is not enough.

ATDD should produce machine-readable evidence:

```txt
which gate ran
which convention set applied
which workspace provider executed
which implementation produced the result
which violations remain
which artifacts were checked
```

### ATDD standardizes the definition of done.

The point is not only to run tests. The point is to define what “done” means for a delivery unit.

Done means the relevant conventions were applied, the relevant gates ran, violations were resolved or accepted according to policy, and evidence was produced.

### ATDD gives weaker agents stronger rails.

A very smart agent may infer many project conventions. A weaker agent may not.

ATDD reduces the gap by making the delivery environment explicit.

The goal is not to eliminate intelligence. The goal is to reduce the amount of intelligence required to deliver correctly.

### ATDD makes the system smarter, not only the agent.

The current market often asks: “How do we build smarter agents?”

ATDD asks: “How do we build a smarter delivery system so agents do not need to guess?”

---

## 5. What ATDD is

ATDD is a software delivery protocol that binds together:

- **intent** — what the delivery unit is trying to achieve;
- **conventions** — the explicit rules and expectations;
- **scopes** — where rules apply;
- **gates** — when rules run;
- **extensions** — installable use-case/rule packages;
- **workspace providers** — reusable runtime contracts;
- **workspace instances** — materialized execution environments;
- **implementations** — executable units that realize convention behavior;
- **violations** — machine-readable failures tied to rule IDs;
- **evidence** — machine-readable proof that delivery gates ran and what they produced.

ATDD is the connective protocol between human intent, agent execution, validator feedback, and delivery evidence.

---

## 6. What ATDD is not

ATDD should not become:

- a new CI/CD engine;
- a new static analyzer;
- a new policy language;
- a new agent framework;
- a new package manager;
- a new developer portal;
- a new supply-chain attestation framework.

Those categories already exist and should be reused.

ATDD should define how they plug into a common delivery protocol.

---

## 7. The architectural spine

### Extension

An **extension** is the installable use-case package.

It owns:

- conventions;
- scopes;
- gates;
- rule IDs;
- ownership boundaries;
- implementation references.

An extension answers:

```txt
What delivery behavior are we adding?
What rules does this package own?
Where do they apply?
When do they run?
```

### Convention

A **convention** is a declarative rule or expectation.

It is not necessarily executable by itself. It is the normative delivery statement.

### Scope

A **scope** defines where a convention applies.

Examples:

```txt
all source files
all public API files
all migration files
all test files
all files in a component boundary
```

### Gate

A **gate** defines when a convention is enforced.

Examples:

```txt
pre-commit
pre-push
pull request
ci
release
migration
agent handoff
```

### Workspace Provider

A **workspace provider** is a reusable runtime contract.

Examples:

```txt
atdd.workspace.python-pytest
atdd.workspace.node-vitest
atdd.workspace.go-test
atdd.workspace.opa
atdd.workspace.semgrep
```

The provider owns how executable units run, not why they matter.

### Workspace Instance

A **workspace instance** is the resolved/materialized runtime used during execution.

It is the concrete local execution environment created from a workspace provider.

### Implementation

An **implementation** is the executable unit that realizes a convention.

Today, most implementations may be validators.

But the layer should remain generic:

```yaml
kind: implementation
type: validator
```

Future implementation types may include:

```txt
validator
fixer
generator
reporter
migrator
collector
test
```

### Violation

A **violation** is a machine-readable failure tied to a rule ID.

It should point back to the convention that was broken.

### Evidence

**Evidence** is the machine-readable proof of execution and result.

It should answer:

```txt
What ran?
Against what?
Under which convention set?
Using which runtime?
With what result?
```

---

## 8. The first-class workspace provider decision

Reusable runtimes should be first-class from the beginning.

ATDD should not encourage every extension to copy its own `python-pytest` runtime folder.

That would create:

- duplicated runtimes;
- version drift;
- inconsistent commands;
- inconsistent discovery behavior;
- painful migration once extensions proliferate.

The recommended model is:

```txt
Extension
  owns the use case and rule IDs

Workspace Provider
  owns the reusable runtime contract

Workspace Instance
  is materialized during execution

Implementation
  targets a workspace provider and emits violations/evidence
```

Embedded workspaces may remain allowed for private or unusual runtimes, but official/common runtimes should be shared providers by default.

---

## 9. Relationship to agents

ATDD is agent-compatible, but not agent-dependent.

A human can use ATDD. A CI system can use ATDD. A coding agent can use ATDD. A coach/worker multi-agent system can use ATDD.

The protocol is the stable part.

The intelligence of the actor is variable.

That is the point.

ATDD makes delivery behavior portable across actors.

---

## 10. The delivery loop

The ATDD loop is:

```txt
1. Extension declares conventions, scopes, and gates.
2. Implementation declares which rule IDs it enforces.
3. Workspace provider supplies the runtime contract.
4. Workspace instance executes the implementation.
5. Implementation emits violations or evidence.
6. Agent/human/system uses feedback to repair or accept the delivery state.
7. Gate result becomes part of the delivery record.
```

This is the closed loop:

```txt
Declarative rule + executable implementation + reusable runtime + evidence = delivery protocol
```

---

## 11. The non-negotiables

ATDD should be:

- explicit;
- machine-readable;
- composable;
- runtime-agnostic;
- agent-agnostic;
- CI-agnostic;
- evidence-producing;
- convention-centered;
- implementation-backed;
- strict about ownership boundaries.

ATDD should avoid:

- hidden rules;
- unversioned runtime behavior;
- ambiguous “done” states;
- agent-only assumptions;
- duplicated workspace runtimes;
- vague validation output;
- tool lock-in.

---

## 12. Final manifesto statement

ATDD is the missing software delivery protocol for a world where humans, agents, and automation all contribute to software production.

It does not bet everything on smarter agents.

It bets on a smarter delivery system.

It replaces invisible expectations with explicit conventions.

It replaces informal confidence with executable gates.

It replaces vibes with violations and evidence.

It lets weaker agents deliver stronger software because the system carries more of the delivery intelligence.

**Protocol, not platform. Contracts, not vibes. Evidence, not confidence.**
