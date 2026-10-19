# ADR 0001: Modular monolith on native Windows

Status: Accepted

Context: This is a learning/portfolio system developed on an 8 GB Windows machine.

Decision: Use apps/api and apps/web in one repository, with independently installed
Python and npm dependencies. Use native processes, no containers, WSL, local database,
or local model. Keep domain logic independent of infrastructure as features appear.
Introduce independent MCP servers only when actual integrations need them.

Consequences: Low local overhead and simple debugging. Separate Python and Node toolchains
remain necessary. This foundation is not a production security or deployment design.
