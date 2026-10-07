# Local OCR

A Python script, with a simple browser app, to transcribe PDFs and images with a local Ollama vision model. Designed for use by historians and academics.

## AI declaration
The code for this project was generated using Claude Code (Sonnet 5.5). This readme 
file was generated from the Claude Code project and then edited by James Poskett.

## Benefits

- Privacy (images do not leave your computer)
- Rights (no external AI model training)
- Cost (no payment for commercial service)
- Reproducability (specific models can be selected and pinned)

## Requirements

- Python 3.10+
- Python packages in requirements.txt
- [Ollama](https://ollama.com) running locally, with a vision-capable model
  pulled (e.g. `ollama pull qwen3-vl:8b-instruct-q4_K_M`)

## Install

Download the latest release of this repo (including app.py, local_ocr.py, and requirements.txt).

```
brew install poppler
pip install -r requirements.txt
ollama pull qwen3-vl:8b-instruct-q4_K_M
```

Ollama must be installed and running (the desktop app, or `ollama serve`).

## Use

### App

```
streamlit run app.py
```


### Terminal

```
python local_ocr.py /path/to/folder
python local_ocr.py scan.pdf --document-type handwriting
python local_ocr.py /path/to/folder --language "early modern Latin" --model gemma4:26b-a4b-it-q4_K_M
python local_ocr.py /path/to/folder --option num_predict=8192 --option seed=1
caffeinate -i python local_ocr.py /path/to/folder
```

Document types (`--document-type`): `auto` (default), `printed`, `handwriting`. Use `--prompt` or `--prompt-file` for your own.

Default model options: temperature 0.2, repeat_penalty 1.3, num_predict 4096 (maximum tokens per page; stops a looping model), num_ctx 8192. Override any with `--option key=value`.

## Output

Each run goes into a project folder, by default `~/Documents/OCR/<input folder name>/` (choose another with `--output`, or type a project name in the app). The original files are copied in, so every image sits next to its transcript:

```
~/Documents/OCR/
  Box 12 Letters/
    manifest.csv
    logs/run_log_2026-10-06_141244.txt
    prompts/623494842f.txt
    IMG_0001.jpg
    IMG_0001.txt
    Folder A/                 sub-folders of the input are kept
      IMG_0100.jpg
      IMG_0100.txt
    Letter 1745/              one folder per PDF
      Letter 1745.pdf
      page_0001.png
      page_0001.txt
```

- `manifest.csv`: one row per page attempt (model, model digest, prompt, options, status, timing). The model is recorded here rather than in the folder name.
- `logs/`: the same progress lines you see on screen, with ETA. Each run starts a new log, so a resumed run gets its own file.
- `prompts/`: the exact prompt used, named by the hash in the manifest.
- If two images in one folder share a name (`IMG_1.jpg` and `IMG_1.png`), their transcripts keep the extension (`IMG_1_jpg.txt`, `IMG_1_png.txt`) so they never clash.
- `converted/`: PNG copies of TIFFs, and of any image resized with `--max-side`, which is what the model actually reads.

To compare models on the same material, use a different project name for each model. Resuming skips any page that already has a `.txt`, whichever model wrote it.

## Stopping and resuming

Press Ctrl+C at any time (or stop the run in the app). Finished pages are saved. Run the same command again to continue; pages that already have a `.txt` are skipped and pages that failed are retried. Use `--overwrite` to redo everything (the manifest gains new rows; it is a log, not a summary).

If 5 pages in a row fail (for example because Ollama has quit), the run stops with a message instead of logging thousands of errors. Change the number with `--max-errors N`, or use `--max-errors 0` to never stop. Run the same command again to resume.

## Checking the results

- In the manifest, filter `status` for `warning` (empty, "[no text identified]", or truncated at num_predict) and `error`.
- Vision models can silently modernise spelling, expand abbreviations or invent plausible text. Compare a sample of pages against the originals before trusting a whole collection, and test printed and handwritten material separately.
- Use non-thinking (instruct) vision models. Thinking models can use up `num_predict` before transcribing. If a model produces 300 thinking tokens without starting a transcript, the page is abandoned; change the limit with `--max-think-tokens N` (`0` disables it).
- Multi-page TIFFs: only the first frame is read.

## License

MIT — see [LICENSE](LICENSE).