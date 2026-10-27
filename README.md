# NoteTakingApp
Uses offline LLM model to take notes in PDF, Audio and Video formats. Creates notes, reference from pdf's and Videos, give exam preparation questions(mcq's, short and long answers), create python script and code explanation all in one UI.

Turns lecture recordings, slides (PDF), videos and YouTube links into study notes with
short / medium / long explanations, pictures, references, exam questions and runnable Python scripts.
Everything runs locally with open-source models. Only downloading a YouTube video needs internet.

## Features
- **Inputs:** record audio in the browser, upload audio (mp3, wav, m4a, ogg, opus, flac, webm, aac, wma)
  or video (mp4, mkv, webm, mov, avi), paste a YouTube link, and/or upload the lecture PDF.
- **Audio/video + PDF:** the speech is matched to the slide it talks about.
- **Notes per section:** short, medium and long explanations, key points, key terms, slide pictures or
  video screenshots, references (slide numbers, clickable video timestamps) and further reading.
- **Exam questions:** multiple choice (with instant checking), short answer and long answer, with model answers.
- **Python Lab:** a runnable script for each section with a full line-by-line explanation. Edit it and
  run it in the app; printed output and charts are shown. Generated scripts are test-run and fixed automatically.
- **Runs in the background:** browse other lectures while one is generated; live progress, time left
  and expected finish time; cancel and resume.
- **Folders:** organise lectures into folders, move them, search.
- **Export:** Markdown, HTML (print to PDF from the browser) and the transcript.

## Requirements
- Windows 10/11 (other systems should work but are untested)
- An NVIDIA GPU with 12 GB memory is recommended (tested on an RTX 4070). Without one it works but is much slower.
- About 20 GB of free disk space for the models

## Setup (once)
```powershell
# 1. Tools
winget install Ollama.Ollama
winget install astral-sh.uv

# 2. AI models (about 16 GB)
ollama pull qwen3:14b
ollama pull qwen2.5vl:7b
ollama pull nomic-embed-text

# 3. Python environment
uv venv venv --python 3.12
uv pip install --python venv\Scripts\python.exe -r requirements.txt
```
The Whisper speech model (about 1.6 GB) downloads automatically the first time you transcribe audio,
into `models/whisper`. After setup everything works offline.

## Start
Double-click **`run_app.bat`**, or in PowerShell:
```powershell
venv\Scripts\Activate.ps1
streamlit run NoteTakingApp.py
```
The app opens at http://localhost:8501. To use it from your phone on the same Wi-Fi, open the
"Network URL" printed in the terminal (Windows may ask to allow Python through the firewall).

## Models (all local)
| Job | Model |
|---|---|
| Speech to text | Whisper large-v3-turbo (faster-whisper, GPU) |
| Notes, questions, code | `qwen3:14b` via Ollama |
| Slide pictures & video frames | `qwen2.5vl:7b` via Ollama |
| Matching speech to slides | `nomic-embed-text` via Ollama |

Change models in [config.py](config.py). For a slower PC, try `qwen3:8b` (`ollama pull qwen3:8b`).

## Typical times (RTX 4070, 74-minute lecture with 64 slides)
| Input | Time |
|---|---|
| Slides only | ~15 min |
| YouTube link or video file | ~12–14 min |
| Audio/video + slides | ~19–21 min |
| + Python scripts for every section | ~+5 min |

Most of the time is the AI writing text. Turning off "Create exam questions now" saves about a third.

## Project layout
```
NoteTakingApp.py        the UI (Streamlit)
config.py               settings (models, limits)
run_app.bat             starts Ollama (if needed) and the app
core/
  pipeline.py           runs every step in order; can resume a stopped lecture
  jobs.py               background generation queue (cancel / resume / progress)
  timer.py              time-left estimate
  transcriber.py        speech → text (Whisper)
  pdf_processor.py      PDF → text + page pictures
  youtube_processor.py  YouTube download (with retries) + captions
  media.py              video frames and media length
  vision.py             describes pictures (vision model)
  aligner.py            matches speech to slides
  notes_generator.py    sections + short/medium/long notes + references
  quiz_generator.py     exam questions
  code_generator.py     Python scripts + explanations (tested and auto-fixed)
  code_runner.py        runs scripts, captures output and charts
  mathfix.py            repairs LaTeX maths damaged in the model's JSON answers
  storage.py            saves lectures and folders, exports Markdown/HTML
  llm.py                talks to Ollama
  gpu.py                makes the CUDA libraries visible to Whisper on Windows
tests/
  make_samples.py       small sample lecture (PDF + spoken WAV)
  test_pipeline.py      end-to-end run on the sample
  test_ui.py            every page renders without errors
  test_folders.py       folders: create / rename / delete / move
  test_mathfix.py       LaTeX repair
  test_matrix.py        every input combination and file format on a real lecture
data/                   your lectures (not in git)
models/                 Whisper model (not in git)
```

## Notes
- The **Python Lab** runs scripts on your PC with a time limit, but it is not a sandbox.
  Only run code you trust.
- "Further reading" is suggested by the AI and may be wrong. The references (slide numbers,
  timestamps) come from your own material.
- Generation stops if the app's terminal window is closed; open the lecture and click **Resume**.
