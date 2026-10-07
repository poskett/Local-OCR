# Declaration: Code generated using Anthropic Claude (Opus 5.5)
import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

import ollama
import pandas as pd
import streamlit as st

from local_ocr import DEFAULT_MODEL, DEFAULT_OCR_FOLDER, DEFAULT_OPTIONS, PROMPTS

APP_DIR = Path(__file__).resolve().parent
SCRIPT = APP_DIR / "local_ocr.py"
SETTINGS_FILE = APP_DIR / "settings.json"
SETTING_DEFAULTS = {
    "document_type": next(iter(PROMPTS)),
    "language": "",
    "temperature": float(DEFAULT_OPTIONS["temperature"]),
    "repeat_penalty": float(DEFAULT_OPTIONS["repeat_penalty"]),
    "num_predict": int(DEFAULT_OPTIONS["num_predict"]),
    "num_ctx": int(DEFAULT_OPTIONS["num_ctx"]),
    "keep_alive": "",
    "dpi": 200,
    "max_side": 0,
    "retries": 2,
    "max_think_tokens": 300,
    "max_errors": 5,
    "overwrite": False,
    "ocr_folder_text": str(DEFAULT_OCR_FOLDER),
}
SETTING_LIMITS = {
    "temperature": (0.0, 1.5),
    "repeat_penalty": (1.0, 2.0),
    "num_predict": (256, 32768),
    "num_ctx": (2048, 131072),
    "dpi": (72, 600),
    "max_side": (0, 10000),
    "retries": (0, 10),
    "max_think_tokens": (0, 10000),
    "max_errors": (0, 100),
}
UPLOAD_TYPES = ["pdf", "png", "jpg", "jpeg", "tif", "tiff"]
MAX_UPLOAD_MB = 2000
PROGRESS_PATTERN = re.compile(r"\[(\d+)/(\d+)\]")

st.set_page_config(page_title="Local OCR", page_icon="📜", layout="wide")

for key, value in {"proc": None, "log_lines": [], "output_dir": None, "command": None, "return_code": None, "upload_dir": None}.items():
    if key not in st.session_state:
        st.session_state[key] = value


def load_settings():
    try:
        data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save_settings(settings):
    SETTINGS_FILE.write_text(json.dumps(settings, indent=2, ensure_ascii=False), encoding="utf-8")


def saved_value_is_usable(key, value):
    default = SETTING_DEFAULTS[key]
    if key == "document_type":
        return value in PROMPTS
    if isinstance(default, bool):
        return isinstance(value, bool)
    if isinstance(default, str):
        return isinstance(value, str)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    low, high = SETTING_LIMITS[key]
    return low <= value <= high


def apply_saved_settings(saved):
    for key, default in SETTING_DEFAULTS.items():
        value = saved.get(key)
        if key not in st.session_state:
            usable = key in saved and saved_value_is_usable(key, value)
            st.session_state[key] = type(default)(value) if usable else default
    saved_prompts = saved.get("prompts")
    if not isinstance(saved_prompts, dict):
        saved_prompts = {}
    for name, default_prompt in PROMPTS.items():
        text = saved_prompts.get(name)
        st.session_state.setdefault(f"prompt_{name}", text if isinstance(text, str) else default_prompt)


def reset_settings():
    SETTINGS_FILE.unlink(missing_ok=True)
    for key in [*SETTING_DEFAULTS, "model", *[f"prompt_{name}" for name in PROMPTS]]:
        st.session_state.pop(key, None)


@st.cache_data(ttl=60, show_spinner=False)
def list_models():
    names = [entry["model"] for entry in ollama.list()["models"]]
    vision = []
    for name in names:
        try:
            capabilities = getattr(ollama.show(name), "capabilities", None) or []
        except Exception:
            capabilities = []
        if "vision" in capabilities:
            vision.append(name)
    return sorted(vision or names)


def upload_parts(uploaded):
    return [p for p in Path(uploaded.name).parts if p not in ("", ".", "..", "/")]


def common_top_folder(uploaded_files):
    tops = {tuple(upload_parts(u)[:1]) for u in uploaded_files if len(upload_parts(u)) > 1}
    flat = any(len(upload_parts(u)) == 1 for u in uploaded_files)
    if len(tops) == 1 and not flat:
        return tops.pop()[0]
    return None


def suggest_project_name(uploaded_files, input_path_text):
    if input_path_text.strip():
        path = Path(input_path_text.strip()).expanduser()
        return path.stem if path.suffix else path.name
    if not uploaded_files:
        return ""
    top = common_top_folder(uploaded_files)
    if top:
        return top
    if len(uploaded_files) == 1:
        return Path(uploaded_files[0].name).stem
    return f"Upload {date.today().isoformat()}"


def clean_project_name(name):
    return name.replace("/", "-").replace(":", "-").strip(" .")


def save_uploads(uploaded_files):
    batch_dir = Path(tempfile.mkdtemp(prefix="local_ocr_"))
    for uploaded in uploaded_files:
        target = batch_dir.joinpath(*upload_parts(uploaded))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(uploaded.getbuffer())
    return batch_dir


def start_run(command, output_dir):
    env = dict(os.environ, PYTHONUNBUFFERED="1")
    st.session_state.proc = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        cwd=APP_DIR,
        env=env,
    )
    st.session_state.log_lines = []
    st.session_state.output_dir = output_dir
    st.session_state.command = command
    st.session_state.return_code = None


def follow_run():
    proc = st.session_state.proc
    lines = st.session_state.log_lines
    progress = st.progress(0.0, text="Starting…")
    log_box = st.empty()
    for line in proc.stdout:
        lines.append(line.rstrip())
        match = PROGRESS_PATTERN.search(line)
        if match:
            done, total = int(match.group(1)), int(match.group(2))
            progress.progress(min(done / total, 1.0), text=f"Page {done} of {total}")
        log_box.code("\n".join(lines[-300:]), language=None, height=320)
    proc.wait()
    if st.session_state.upload_dir:
        shutil.rmtree(st.session_state.upload_dir, ignore_errors=True)
        st.session_state.upload_dir = None
    st.session_state.return_code = proc.returncode
    st.session_state.proc = None
    st.rerun()


def show_results(output_dir):
    manifest_path = output_dir / "manifest.csv"
    if not manifest_path.exists():
        return
    manifest = pd.read_csv(manifest_path)
    latest = manifest.drop_duplicates(subset=["source_file", "page"], keep="last")
    counts = latest["status"].value_counts()

    st.subheader("Results")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Pages", len(latest))
    col2.metric("OK", int(counts.get("ok", 0)))
    col3.metric("Warnings", int(counts.get("warning", 0)))
    col4.metric("Errors", int(counts.get("error", 0)))

    st.caption(f"Output folder: `{output_dir}`")
    if st.button("Open output folder", icon=":material/folder_open:"):
        subprocess.run(["open", str(output_dir)])

    st.dataframe(
        latest[["source_file", "page", "status", "chars", "seconds", "error", "timestamp"]],
        hide_index=True,
        width="stretch",
    )

    readable = latest[latest["txt_path"].notna() & (latest["txt_path"] != "")]
    if readable.empty:
        return
    labels = [f"{row.source_file} — page {row.page}" for row in readable.itertuples()]
    choice = st.selectbox("Preview a transcript", labels)
    row = readable.iloc[labels.index(choice)]
    image_col, text_col = st.columns(2)
    image_path = Path(str(row["image_path"]))
    if image_path.exists():
        image_col.image(str(image_path), width="stretch")
    else:
        image_col.info("Page image not available.")
    txt_path = Path(row["txt_path"])
    if txt_path.exists():
        text_col.text_area("Transcript", txt_path.read_text(encoding="utf-8"), height=600, disabled=True)


saved_settings = load_settings()
apply_saved_settings(saved_settings)

with st.sidebar:
    st.header("Settings")

    try:
        models = list_models()
        model_error = None
    except Exception:
        models = [DEFAULT_MODEL]
        model_error = "Cannot reach Ollama. Start it with `ollama serve`, then reload."
    if model_error:
        st.error(model_error)
    if st.session_state.get("model") not in models:
        wanted = saved_settings.get("model")
        if wanted in models:
            st.session_state.model = wanted
        else:
            st.session_state.model = DEFAULT_MODEL if DEFAULT_MODEL in models else models[0]
    model = st.selectbox("Model", models, key="model")
    if st.button("Refresh model list", icon=":material/refresh:", type="tertiary"):
        list_models.clear()
        st.rerun()

    document_type = st.selectbox(
        "Document type",
        list(PROMPTS),
        format_func=lambda name: name.capitalize(),
        key="document_type",
    )
    language = st.text_input("Language (optional)", placeholder="e.g. early modern Latin", key="language")

    with st.expander("Prompt"):
        prompt_text = st.text_area(
            "Prompt sent to the model",
            height=260,
            key=f"prompt_{document_type}",
        )
        if prompt_text.strip() != PROMPTS[document_type].strip():
            st.caption("Edited — this will be recorded as a custom prompt.")

    with st.expander("Model options"):
        temperature = st.slider("Temperature", 0.0, 1.5, step=0.05, key="temperature")
        repeat_penalty = st.slider("Repeat penalty", 1.0, 2.0, step=0.05, key="repeat_penalty")
        num_predict = st.number_input("Max output tokens (num_predict)", 256, 32768, step=256, key="num_predict")
        num_ctx = st.number_input("Context window (num_ctx)", 2048, 131072, step=1024, key="num_ctx")
        keep_alive = st.text_input("Keep model loaded for", placeholder="e.g. 30m (blank = Ollama default)", key="keep_alive")

    with st.expander("Image and run options"):
        dpi = st.number_input("PDF render DPI", 72, 600, step=25, key="dpi")
        max_side = st.number_input("Shrink longest side to (px, 0 = off)", 0, 10000, step=100, key="max_side")
        retries = st.number_input("Retries per page", 0, 10, key="retries")
        max_think_tokens = st.number_input("Max thinking tokens (0 = no limit)", 0, 10000, step=50, key="max_think_tokens")
        max_errors = st.number_input("Stop after errors in a row (0 = never)", 0, 100, key="max_errors")
        overwrite = st.toggle("Redo pages that already have a transcript", key="overwrite")
        ocr_folder_text = st.text_input("OCR folder (holds all projects)", key="ocr_folder_text")

    st.button("Reset settings to defaults", icon=":material/restart_alt:", type="tertiary", on_click=reset_settings)

current_settings = {key: st.session_state[key] for key in SETTING_DEFAULTS}
current_settings["model"] = saved_settings.get("model", model) if model_error else model
current_settings["prompts"] = {
    name: st.session_state[f"prompt_{name}"]
    for name in PROMPTS
    if st.session_state[f"prompt_{name}"].strip() != PROMPTS[name].strip()
}
if current_settings != saved_settings:
    try:
        save_settings(current_settings)
    except OSError:
        st.sidebar.warning("Could not save settings.json in the app folder.")

st.title("Local OCR")
st.caption("Transcribe PDFs and images with a local vision model through Ollama. Nothing leaves this computer.")

running = st.session_state.proc is not None

with st.container(border=True):
    input_mode = st.segmented_control(
        "Input",
        ["Files", "Folder", "Path on disk"],
        default="Files",
        disabled=running,
    )
    uploaded_files = []
    input_path_text = ""
    if input_mode == "Files":
        uploaded_files = st.file_uploader(
            "Drop PDFs or images here",
            type=UPLOAD_TYPES,
            accept_multiple_files=True,
            max_upload_size=MAX_UPLOAD_MB,
            disabled=running,
        )
    elif input_mode == "Folder":
        uploaded_files = st.file_uploader(
            "Drop a folder here",
            type=UPLOAD_TYPES,
            accept_multiple_files="directory",
            max_upload_size=MAX_UPLOAD_MB,
            disabled=running,
        )
    elif input_mode == "Path on disk":
        input_path_text = st.text_input(
            "File or folder path",
            placeholder="/Users/you/Archive/Box 12",
            disabled=running,
        )
        st.caption("Useful for very large collections: no upload needed. The files are copied into the project folder.")

    suggested_name = suggest_project_name(uploaded_files, input_path_text)
    project_text = st.text_input(
        "Project name",
        placeholder=suggested_name or "e.g. Box 12 Letters",
        disabled=running,
    )
    project_name = clean_project_name(project_text or suggested_name)
    ocr_folder = Path(ocr_folder_text.strip() or DEFAULT_OCR_FOLDER).expanduser()
    if project_name:
        st.caption(f"Saved to `{ocr_folder / project_name}`")

    has_input = (bool(uploaded_files) or bool(input_path_text.strip())) and bool(project_name)
    run_col, stop_col, _ = st.columns([1, 1, 4])
    run_clicked = run_col.button(
        "Run OCR", type="primary", icon=":material/play_arrow:",
        disabled=running or not has_input, width="stretch",
    )
    stop_clicked = stop_col.button(
        "Stop", icon=":material/stop:", disabled=not running, width="stretch",
    )

if stop_clicked and st.session_state.proc is not None:
    st.session_state.proc.send_signal(signal.SIGINT)

if run_clicked:
    if input_mode == "Path on disk":
        input_path = Path(input_path_text.strip()).expanduser().resolve()
        if not input_path.exists():
            st.error(f"Not found: {input_path}")
            st.stop()
        st.session_state.upload_dir = None
    else:
        upload_dir = save_uploads(uploaded_files)
        st.session_state.upload_dir = upload_dir
        top = common_top_folder(uploaded_files)
        input_path = upload_dir / top if top else upload_dir
    output_dir = (ocr_folder / project_name).resolve()

    command = [
        sys.executable, str(SCRIPT), str(input_path),
        "--output", str(output_dir),
        "--model", model,
        "--document-type", document_type,
        "--option", f"temperature={temperature}",
        "--option", f"repeat_penalty={repeat_penalty}",
        "--option", f"num_predict={int(num_predict)}",
        "--option", f"num_ctx={int(num_ctx)}",
        "--dpi", str(int(dpi)),
        "--retries", str(int(retries)),
        "--max-think-tokens", str(int(max_think_tokens)),
        "--max-errors", str(int(max_errors)),
    ]
    if prompt_text.strip() != PROMPTS[document_type].strip():
        command += ["--prompt", prompt_text.strip()]
    if language.strip():
        command += ["--language", language.strip()]
    if max_side:
        command += ["--max-side", str(int(max_side))]
    if keep_alive.strip():
        command += ["--keep-alive", keep_alive.strip()]
    if overwrite:
        command.append("--overwrite")

    start_run(command, output_dir)
    st.rerun()

if st.session_state.command:
    with st.expander("Equivalent terminal command"):
        st.code(shlex.join(["python"] + st.session_state.command[1:]), language="bash")

if st.session_state.proc is not None:
    follow_run()
elif st.session_state.log_lines:
    stopped_early = any("Interrupted" in line or "Stopping:" in line for line in st.session_state.log_lines)
    if st.session_state.return_code == 0 and not stopped_early:
        st.success("Run finished.")
    else:
        st.warning("Run stopped before the end — see the log below. Run again with the same settings to resume.")
    with st.expander("Log", expanded=st.session_state.return_code != 0):
        st.code("\n".join(st.session_state.log_lines), language=None, height=320)

if st.session_state.output_dir and st.session_state.proc is None:
    show_results(st.session_state.output_dir)
