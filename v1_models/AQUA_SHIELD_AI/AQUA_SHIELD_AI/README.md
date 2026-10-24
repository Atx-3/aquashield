# AQUA SHIELD AI - Intent & Tool Routing Layer

This module provides the natural language intent routing layer for the **AQUA SHIELD AI** maritime oil spill investigation system. It translates plain text user requests into strictly validated function calls using a locally hosted **Qwen3 1.7B** model via **Ollama**.

---

## Allowed AQUA SHIELD Investigation Tools

The LLM is strictly constrained to the following 8 investigation tools (or `unsupported` for out-of-scope requests):

| Tool / Intent | Purpose | Supported Arguments |
| :--- | :--- | :--- |
| `analyze_spill` | Analyze detected oil slick features, area, thickness, or imagery. | `spill_id` (str), `timestamp` (str) |
| `find_probable_origin` | Reverse drift / backtrack simulation to find probable slick source. | `spill_id` (str), `hours` (num) |
| `find_nearby_vessels` | Search for vessels in the vicinity of the spill location. | `radius_km` (num), `hours` (num), `spill_id` (str) |
| `get_vessel_trajectory` | Retrieve historical AIS track for a specified vessel. | `vessel_id` (str), `hours` (num) |
| `compare_vessels` | Compare suspect vessels against spill corridor & timeline. | `vessel_ids` (list), `criteria` (str) |
| `forecast_spill` | Run forward drift simulation to predict future slick dispersion. | `forecast_hours` (num), `spill_id` (str) |
| `get_evidence` | Gather forensic evidence dossier & correlation proof. | `vessel_id` (str), `spill_id` (str) |
| `generate_report` | Generate official investigation report or summary PDF. | `report_type` (str), `spill_id` (str) |
| `unsupported` | Fallback for non-investigation queries or greetings. | (None) |

> **Safety Rule**: The LLM does **not** perform scientific computations or invent fake investigation results. Arguments are extracted **only** when explicitly provided in the user prompt.

---

## How Ollama is Used

The module communicates with the local Ollama daemon via its HTTP REST API (`/api/generate` and `/api/chat`).

All Ollama communication is encapsulated in [`app/llm.py`](app/llm.py) via the `OllamaClient` class.

### Configuration & Environment Variables

| Variable | Description | Default |
| :--- | :--- | :--- |
| `OLLAMA_HOST` | Ollama service endpoint URL | `http://127.0.0.1:11434` |
| `OLLAMA_MODEL` | Target model name in Ollama | `qwen3:1.7b` |
| `OLLAMA_TIMEOUT` | HTTP request timeout in seconds | `90` |

---

## Ensuring Qwen3 1.7B is Available

1. **Verify Ollama is running**:
   ```bash
   ollama serve
   ```
2. **Pull the Qwen3 1.7B model**:
   ```bash
   ollama pull qwen3:1.7b
   ```
3. **Verify model is installed**:
   ```bash
   ollama list
   ```

---

## Project Structure

```
SIH/
├── app/
│   ├── __init__.py          # Package exports
│   ├── llm.py              # Modular Ollama HTTP client & configurable timeout
│   ├── prompts.py          # System instructions and few-shot routing prompt
│   ├── router.py           # Core router, JSON validation, and pipeline logger
│   ├── tools.py            # 8 tool definitions & argument sanitizers
│   └── response.py         # Structured response dataclass & serializers
├── tests/
│   ├── __init__.py
│   ├── test_router.py      # Standalone unit tests (mocked Ollama, instant execution)
│   └── test_integration.py # Live Ollama integration tests (opt-in)
├── main.py                 # Interactive CLI shell (default) and single-query runner
├── README.md               # Documentation
└── requirements.txt        # Zero external dependencies (Python stdlib)
```

---

## Usage

### 1. Interactive CLI (Default)
Run `python main.py` to launch the interactive prompt. You can enter queries manually and see real-time pipeline logging and structured JSON responses:
```bash
python main.py
```
Type `exit` or `quit` to exit.

### 2. Single Query Execution
Execute a one-off query against the live model:
```bash
python main.py --query "Show me vessels near the spill."
```

### 3. Running Unit Tests (Mocked / Offline)
Run unit tests instantly without needing a running Ollama daemon:
```bash
python -m unittest discover -s tests -p "test_router.py" -v
```

### 4. Running Live Integration Tests (Live Ollama)
To run the live integration tests against the local Ollama instance:
```bash
# Windows PowerShell
$env:RUN_LIVE_TESTS="1"; python -m unittest discover -s tests -p "test_integration.py" -v; Remove-Item Env:\RUN_LIVE_TESTS

# Linux / macOS
RUN_LIVE_TESTS=1 python -m unittest discover -s tests -p "test_integration.py" -v
```

---

## Example Inputs and Expected JSON Outputs

### Example 1: Basic nearby search
**Input**:
```
"Show me vessels near the spill."
```
**Output**:
```json
{
  "intent": "find_nearby_vessels",
  "arguments": {}
}
```

---

### Example 2: Nearby search with explicit radius
**Input**:
```
"Find vessels within 20 km of the spill."
```
**Output**:
```json
{
  "intent": "find_nearby_vessels",
  "arguments": {
    "radius_km": 20
  }
}
```

---

### Example 3: Forward drift forecasting
**Input**:
```
"Where will the spill drift in the next 24 hours?"
```
**Output**:
```json
{
  "intent": "forecast_spill",
  "arguments": {
    "forecast_hours": 24
  }
}
```

---

### Example 4: Vessel trajectory lookup
**Input**:
```
"Show me the path of vessel Ocean Voyager."
```
**Output**:
```json
{
  "intent": "get_vessel_trajectory",
  "arguments": {
    "vessel_id": "Ocean Voyager"
  }
}
```

---

### Example 5: Reverse drift / origin backtracking
**Input**:
```
"Where did this oil spill come from? Backtrack 12 hours."
```
**Output**:
```json
{
  "intent": "find_probable_origin",
  "arguments": {
    "hours": 12
  }
}
```

---

### Example 6: Unsupported / out-of-scope query
**Input**:
```
"What is the capital of France?"
```
**Output**:
```json
{
  "intent": "unsupported",
  "arguments": {},
  "message": "I can only help with AQUA SHIELD investigation commands."
}
```

---

## Pipeline Logging

Each routing execution logs the full trace:
```
--------------------------------------------------
USER INPUT: Find vessels within 20 km of the spill.
-> LLM OUTPUT: {"intent": "find_nearby_vessels", "arguments": {"radius_km": 20}}
-> VALIDATED INTENT: find_nearby_vessels
-> ARGUMENTS: {"radius_km": 20}
--------------------------------------------------
```
