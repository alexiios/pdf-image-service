import os
import re
import shutil
import subprocess
from pathlib import Path
from tempfile import mkdtemp

import img2pdf
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse
from starlette.background import BackgroundTask

app = FastAPI(title="PDF Image-Only Converter")

MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "80"))
MAX_BYTES = MAX_UPLOAD_MB * 1024 * 1024
CONVERT_TIMEOUT_SECONDS = int(os.getenv("CONVERT_TIMEOUT_SECONDS", "900"))
ACCESS_PASSWORD = os.getenv("ACCESS_PASSWORD", "").strip()

HTML = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>PDF转纯图片版PDF</title>
  <style>
    body {{
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: #f6f7f9;
      color: #202124;
    }}
    .wrap {{
      max-width: 760px;
      margin: 56px auto;
      padding: 0 20px;
    }}
    .card {{
      background: #fff;
      border-radius: 18px;
      padding: 28px;
      box-shadow: 0 10px 30px rgba(0,0,0,.08);
    }}
    h1 {{
      margin: 0 0 10px;
      font-size: 28px;
      line-height: 1.3;
    }}
    p {{
      color: #5f6368;
      line-height: 1.7;
    }}
    label {{
      display: block;
      margin-top: 18px;
      margin-bottom: 8px;
      font-weight: 600;
    }}
    input, select, button {{
      width: 100%;
      box-sizing: border-box;
      font-size: 16px;
    }}
    input[type="file"], input[type="password"], select {{
      border: 1px solid #d9dde3;
      border-radius: 12px;
      padding: 12px;
      background: #fff;
    }}
    button {{
      margin-top: 22px;
      border: 0;
      border-radius: 12px;
      padding: 14px 16px;
      background: #111827;
      color: #fff;
      cursor: pointer;
      font-weight: 700;
    }}
    button:hover {{
      background: #1f2937;
    }}
    .note {{
      margin-top: 18px;
      font-size: 14px;
      color: #6b7280;
    }}
  </style>
</head>
<body>
  <main class="wrap">
    <section class="card">
      <h1>PDF转纯图片版PDF</h1>
      <p>上传PDF后，系统会把每一页转成图片，再重新合成一个新的PDF。转换完成后会直接下载，服务器只使用临时文件。</p>
      <form action="/convert" method="post" enctype="multipart/form-data">
        <label for="pdf">选择PDF文件</label>
        <input id="pdf" type="file" name="pdf" accept="application/pdf,.pdf" required>

        <label for="dpi">清晰度</label>
        <select id="dpi" name="dpi">
          <option value="180">普通，文件较小</option>
          <option value="220" selected>清晰，推荐</option>
          <option value="300">高清，文件较大</option>
        </select>

        <label for="password">访问密码</label>
        <input id="password" type="password" name="password" placeholder="如果管理员设置了密码，请在这里输入">

        <button type="submit">开始转换</button>
      </form>
      <div class="note">当前上传限制：{MAX_UPLOAD_MB}MB。大文件转换会更慢，也会生成更大的PDF。</div>
    </section>
  </main>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
def index():
    return HTML


@app.get("/health", response_class=PlainTextResponse)
def health():
    return "ok"


def safe_output_name(filename: str) -> str:
    stem = Path(filename or "converted").stem
    stem = re.sub(r"[^A-Za-z0-9._\-\u4e00-\u9fff]+", "_", stem).strip("._-")
    return f"{stem or 'converted'}_image_only.pdf"


async def save_upload_to_disk(upload: UploadFile, target: Path) -> int:
    total = 0
    with target.open("wb") as f:
        while True:
            chunk = await upload.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_BYTES:
                raise HTTPException(status_code=413, detail=f"文件太大。当前限制为 {MAX_UPLOAD_MB}MB。")
            f.write(chunk)
    return total


def page_num(path: Path) -> int:
    match = re.search(r"-(\d+)\.png$", path.name)
    return int(match.group(1)) if match else 0


@app.post("/convert")
async def convert_pdf(
    pdf: UploadFile = File(...),
    dpi: int = Form(220),
    password: str = Form(""),
):
    if ACCESS_PASSWORD and password != ACCESS_PASSWORD:
        raise HTTPException(status_code=401, detail="访问密码不正确。")

    if dpi not in {180, 220, 300}:
        raise HTTPException(status_code=400, detail="清晰度参数不正确。")

    filename = pdf.filename or "input.pdf"
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="请上传PDF文件。")

    workdir = Path(mkdtemp(prefix="pdf_image_only_"))
    input_pdf = workdir / "input.pdf"
    output_pdf = workdir / "output.pdf"
    pages_dir = workdir / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)

    try:
        await save_upload_to_disk(pdf, input_pdf)

        subprocess.run(
            ["pdftoppm", "-r", str(dpi), "-png", str(input_pdf), str(pages_dir / "page")],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=CONVERT_TIMEOUT_SECONDS,
        )

        image_files = sorted(pages_dir.glob("page-*.png"), key=page_num)
        if not image_files:
            raise HTTPException(status_code=500, detail="没有成功生成页面图片。")

        with output_pdf.open("wb") as f:
            f.write(img2pdf.convert([str(p) for p in image_files]))

        return FileResponse(
            output_pdf,
            media_type="application/pdf",
            filename=safe_output_name(filename),
            background=BackgroundTask(shutil.rmtree, workdir, ignore_errors=True),
        )

    except subprocess.TimeoutExpired:
        shutil.rmtree(workdir, ignore_errors=True)
        raise HTTPException(status_code=504, detail="转换超时。请降低清晰度，或拆分PDF后再试。")
    except subprocess.CalledProcessError as e:
        shutil.rmtree(workdir, ignore_errors=True)
        detail = e.stderr.decode("utf-8", errors="ignore")[-800:] or "PDF转换失败。"
        raise HTTPException(status_code=500, detail=detail)
    except HTTPException:
        shutil.rmtree(workdir, ignore_errors=True)
        raise
    except Exception as e:
        shutil.rmtree(workdir, ignore_errors=True)
        raise HTTPException(status_code=500, detail=f"转换失败：{e}")
