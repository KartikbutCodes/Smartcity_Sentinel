# Ethics, privacy, and responsible use

SmartCity Sentinel is an educational, offline simulation, not a validated safety
system. It must not be used to identify, track, score, or make enforcement
decisions about people. All demo records are synthetic. Event scores are
uncertain signals and require independent human verification.

## Privacy by design

- Prefer aggregate counts and transient track IDs; do not infer identity.
- Blur faces and registration plates in any authorized test footage before
  writing images to disk. The demo has no raw video storage pipeline.
- Do not collect audio, face templates, or plate-to-person mappings.
- Keep data local, apply a documented retention schedule, and limit exports.
- Differential privacy is applied only to aggregate counts. Epsilon must be
  selected and documented for each release; seeded noise is for tests only.
- Hash chaining can expose alteration but is not a trusted timestamp or
  protection against an administrator rewriting the entire file.
- RBAC helpers are examples, not production authentication or authorization.

## Bias and explainability

Detection quality may differ with lighting, camera placement, mobility aids,
clothing, age, or other contextual factors. Evaluate false-positive and
false-negative rates on lawfully collected, representative, consented datasets
before any pilot; suppress or remove a feature when disparities cannot be
mitigated. Group metrics in this demo are illustrative and can themselves
involve sensitive attributes. Never use them to rank individuals.

Scores from the simple anomaly and crowd baselines are not calibrated
probabilities. The demo's explainability output reports deviations, not causal
explanations. Any human review process should record uncertainty and allow
appeal.

## Function creep and legal context (India)

Use must be purpose-limited, necessary, proportionate, transparent, access
controlled, and subject to independent review. A deployment in India must be
assessed against the Digital Personal Data Protection Act, 2023 (DPDP Act), its
rules as applicable, constitutional privacy protections, sector-specific
requirements, and local surveillance and procurement rules. Consult qualified
Indian counsel and the relevant data-protection authority before collecting
personal data. This document is not legal advice. Provide notice, document a
lawful basis, assess data-fiduciary obligations, enable rights and grievance
handling where applicable, and establish breach response and deletion
procedures. Do not treat a public place as consent to unrestricted monitoring.

## Operational guardrails

Keep the system offline, use synthetic data for demonstrations, and never
connect the toy API to public networks. No output should alone trigger
detention, denial of service, or emergency dispatch. Use documented human
authorization, audit access, conduct impact assessments, and shut down when
data quality or governance conditions fail.
