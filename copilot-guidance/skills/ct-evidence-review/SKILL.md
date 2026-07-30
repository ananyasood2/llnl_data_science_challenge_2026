---
name: ct-evidence-review
description: Review deterministic raw-CT evidence for a selected registered strut or node. Use when asked to generate CT evidence, inspect a selected element, or explain visible slice evidence.
---

# CT Evidence Review

1. Require a selected element in the viewport context or an explicit registered
   kind and ID.
2. Call `inspect_element`, then `generate_ct_evidence`.
3. Link the generated evidence action to the existing Dash raw-CT review panel.
4. Report measurements and caveats returned by tools; never send raw CT volumes
   to model context or write source imagery.

