# Local LLM Safety Report Experiment

Experiment code and data for the bachelor's thesis:

**Local LLMs in Manufacturing SMEs: Feasibility, Privacy, and Cybersecurity Assessment**
Inusah Mohammed — Karelia University of Applied Sciences, May 2026

## Repository structure

```
├── run_experiment.py        # Inference automation script
├── README.md
├── LICENSE                  # MIT
│
├── reports/                 # Safety incident reports (input data)
│   ├── INC-2024-047.txt     # Synthetic
│   ├── INC-2024-051.txt     # Synthetic
│   ├── INC-2024-058.txt     # Synthetic
│   ├── INC-2025-003.txt     # Synthetic
│   ├── INC-2025-009.txt     # Synthetic
│   ├── INC-2025-014.txt     # Synthetic
│   ├── INC-2025-028.txt     # Synthetic
│   ├── INC-2025-035.txt     # Synthetic
│   ├── CAF-2024-001.txt     # Real, fully anonymized
│   └── CAF-2025-002.txt     # Real, fully anonymized
│
├── prompts/
│   └── prompts.csv          # Prompt templates (4 task types)
│
├── ground_truth/
│   └── README.md            # Format guide for future annotators
│
└── results/                 # Created automatically on first run
    ├── results.csv          # Quantitative metrics for all 80 runs
    └── responses/           # Full model output for each run (80 .txt files)
```

## Requirements

- Python 3 (standard library only — no pip installs needed)
- [Ollama](https://ollama.com) running on `localhost:11434`
- Models pulled:
  ```
  ollama pull llama3.1:latest
  ollama pull qwen2.5:32b
  ```
- Linux host (system metrics sampled from `/proc/stat` and `/proc/meminfo`)

## Running the experiment

```bash
python3 run_experiment.py
```

Results are written to `results/` automatically. Re-running overwrites
existing results.

## Dataset notes

Eight reports (INC-*) are synthetic and were designed to reflect the
structure and content of real manufacturing safety incident reports without
containing any personal or operational data.

**CAF-2024-001 and CAF-2025-002** are based on real incidents from an aluminium 
fabrication company and have been fully anonymized. The original PDF documents 
are not published to protect the source organization. 
The extracted text files represent the complete content used in the experiment.

The authenticity and representativeness of the synthetic reports were verified by 
a qualified safety professional with experience in manufacturing safety management, 
who confirmed that the reports reflect realistic incident types, language, and 
documentation structure typical of the sector.

## Prompts

Four prompt types are defined in `prompts/prompts.csv`:

| Prompt type | Task |
|---|---|
| Summarization | 3–5 sentence summary of incident type, severity, cause, outcome |
| Risk Classification | Risk level, severity, recurrence likelihood with justification |
| Corrective Action Extraction | Numbered list of all corrective actions stated in the report |
| Root Cause Identification | Root causes with explanation of contribution to incident |

To modify prompts or add new ones, edit `prompts/prompts.csv` directly.
No code changes are required.

## Adding your own reports

Place any `.txt` file in the `reports/` directory. The script loads all
`.txt` files automatically. File names become the report ID in the output.

## Output format

`results/results.csv` columns:

| Column | Description |
|---|---|
| Run | Sequential run number |
| Model | Ollama model identifier |
| Report_ID | Report filename without extension |
| Prompt_Type | Task name from prompts.csv |
| Tokens_Per_Second | Inference throughput (TPS) |
| Total_Time_Seconds | End-to-end response time |
| Tokens_Generated | Output token count |
| Prompt_Tokens | Input token count |
| Eval_Duration_ns | Ollama eval duration in nanoseconds |
| Load_Duration_ns | Model load time in nanoseconds |
| Peak_CPU_Pct | Peak CPU utilisation during run |
| Mean_CPU_Pct | Mean CPU utilisation during run |
| Baseline_RAM_GB | RAM before model load |
| Peak_RAM_GB | Peak RAM during inference |
| Model_Footprint_GB | Peak RAM minus baseline |
| Sample_Count | Number of system metric samples taken |
| Timestamp | ISO 8601 run completion time |

## Ground truth

No ground truth annotations were produced for the original experiment.
See `ground_truth/README.md` for the intended format if you wish to add
annotations for your own evaluation.

## Citation

If you use this dataset or code, please cite:

> Mohammed, I. 2026. Local LLMs in Manufacturing SMEs: Feasibility,
> Privacy, and Cybersecurity Assessment. Bachelor's thesis.
> Karelia University of Applied Sciences, Joensuu, Finland.

## License

MIT — see LICENSE file.
