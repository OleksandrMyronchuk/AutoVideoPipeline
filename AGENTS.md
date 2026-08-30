# Agent Rules

## Rule 1: Flexible script construction

Any modification to the script constructor must be fully generic and resilient to replacement.

- Do not hardcode literal values, script names, story beats, prompts, asset references, or scenario-specific assumptions.
- Do not depend on the current script contents or existing scenario structure.
- Design constructors and pipeline logic so they work even if the entire script and scenario are replaced by a completely different one.
- Prefer parameterized, data-driven behavior over bespoke logic tied to the current project state.
- The implementation should remain valid when scripts, scenes, prompts, and context are deleted and rebuilt from scratch.

## Rule 2: Test cleanup requirement

Tests are allowed to be created and executed during work, but they must be fully removed before completion.

- If a test is created using Python, JavaScript, or any other framework, delete the test file and any related temporary artifacts before finishing.
- Remove generated task folders, scratch files, or ad hoc validation scaffolds that are not part of the final solution.
- Do not leave behind extra files or modified task folders after work is complete.
- Keep the final workspace clean and limited to the intended project state.
