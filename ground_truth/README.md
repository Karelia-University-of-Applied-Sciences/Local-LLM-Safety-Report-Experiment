# Ground Truth

This directory is a placeholder for ground truth annotations.

Ground truth files were not produced as part of the original thesis experiment
due to time constraints. This is acknowledged as a limitation in the thesis
(Section 6.3).

## Intended format

If future evaluators wish to add ground truth, the recommended format is one
CSV file per prompt type, e.g. `Summarization_ground_truth.csv`, with the
following columns:

| Column | Description |
|---|---|
| report_id | Report identifier, e.g. INC-2024-047 |
| expected_output | The reference answer a correct response should match |
| correctness_notes | What a correct response must include to score 3/3 |
| completeness_notes | Required elements for full completeness score |
| relevance_notes | Boundaries of acceptable content (what counts as hallucination) |

## Scoring rubric reference

The rubric used in the thesis is defined in Section 3.3.1 (Table 1).
Scores range from 3 to 9 across three dimensions: correctness,
completeness, and relevance (each scored 1–3).

Responses scoring 7–9 are considered high quality for use in a safety
management workflow with human review. Responses scoring 4–6 require
correction before use. A score of 3 (minimum possible) indicates major
errors, missing elements, or hallucinated content and would require
complete rewriting.

## Example scoring record (illustrative)

The table below shows how a ground truth row would look for the
Summarization prompt type applied to INC-2024-047:

| Column | Example value |
|---|---|
| report_id | INC-2024-047 |
| expected_output | A hydraulic press operator triggered an emergency stop after a pressure spike reached 340 bar, exceeding the 280 bar threshold. The incident was caused by a partial blockage in the hydraulic return line from accumulated metal shavings, compounded by an inline filter overdue for replacement at 623 hours against a 500-hour interval. Severity was minor as no injuries occurred and production halted for 47 minutes. Corrective actions included filter replacement, checklist revision, and operator awareness training. |
| correctness_notes | Must correctly state: 340 bar spike, 280 bar threshold, 500-hour interval exceeded at 623 hours, no injuries, 47-minute production halt. Must not contradict any of these facts. |
| completeness_notes | Must include all four required elements: incident type (pressure spike / near-miss), severity level, immediate cause (filter blockage), and outcome (emergency stop, production halt, no injury). |
| relevance_notes | Must not introduce causes, injuries, or corrective actions not stated in the report. Inferring that the filter was "neglected" or that "maintenance culture was poor" would count as hallucination. |

For worked scoring examples with actual model outputs and
dimension-by-dimension justifications, see Section 4.3.4 of the thesis.
