import os
import base64
import asyncio
import json
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from playwright.async_api import async_playwright

app = FastAPI()

LOGIN_URL  = os.environ.get("LOGIN_URL",  "https://portal.mc.chitose.ac.jp/portal/")
MYPAGE_URL = os.environ.get("MYPAGE_URL", "https://portal.mc.chitose.ac.jp/portal/MyPage")

# ACCOUNTS_JSON 環境変数から読む（Railwayで設定する）
# 例: [{"username":"b2240530","password":"xxx"},{"username":"yyy","password":"zzz"}]
_accounts_raw = os.environ.get("ACCOUNTS_JSON", "[]")
ACCOUNTS: list = json.loads(_accounts_raw)


class InputRequest(BaseModel):
    location: str
    value: str


class DebugRequest(BaseModel):
    location: str


async def run_on_account(account: dict, location: str, value: str) -> str:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        try:
            # ① ログイン
            await page.goto(LOGIN_URL)
            await page.wait_for_load_state("networkidle")
            await page.locator(
                "input[type='text'], input[type='email'], input[name*='id'], input[name*='user']"
            ).first.fill(account["username"])
            await page.locator("input[type='password']").first.fill(account["password"])
            await page.locator(
                "button[type='submit'], input[type='submit'], button:has-text('ログイン')"
            ).first.click()
            await page.wait_for_load_state("networkidle")

            # ② マイページへ移動
            await page.goto(MYPAGE_URL)
            await page.wait_for_load_state("networkidle")

            # ③ 場所をa・buttonから完全一致で探してクリック
            target = page.locator("a, button").filter(has_text=location).first
            await target.wait_for(state="visible", timeout=10000)
            await target.click()
            await page.wait_for_load_state("networkidle")

            # ④ 入力欄を自動検出して入力
            field = page.locator("input:visible, textarea:visible").first
            await field.wait_for(state="visible", timeout=10000)
            await field.fill(value)

            # ⑤ 送信ボタンをクリック
            submit_btn = page.get_by_role("button", name="送信")
            if await submit_btn.count() > 0:
                await submit_btn.first.click()
            else:
                await page.locator("button[type='submit'], input[type='submit']").first.click()
            await page.wait_for_load_state("networkidle")

            return f"✅ {account['username']} 完了"

        except Exception as e:
            return f"❌ {account['username']} エラー: {str(e)}"
        finally:
            await browser.close()


async def run_debug(location: str) -> dict:
    if not ACCOUNTS:
        return {"steps": [{"label": "設定エラー", "url": "", "ok": False, "error": "ACCOUNTS_JSON が未設定です"}], "screenshot": None}

    account = ACCOUNTS[0]
    steps = []
    screenshot = None

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        try:
            # ① ログイン
            await page.goto(LOGIN_URL)
            await page.wait_for_load_state("networkidle")
            await page.locator(
                "input[type='text'], input[type='email'], input[name*='id'], input[name*='user']"
            ).first.fill(account["username"])
            await page.locator("input[type='password']").first.fill(account["password"])
            await page.locator(
                "button[type='submit'], input[type='submit'], button:has-text('ログイン')"
            ).first.click()
            await page.wait_for_load_state("networkidle")
            steps.append({"label": "① ログイン", "url": page.url, "ok": True})

            # ② マイページへ移動
            await page.goto(MYPAGE_URL)
            await page.wait_for_load_state("networkidle")
            steps.append({"label": "② マイページ移動", "url": page.url, "ok": True})

            # ③ 場所クリック
            target = page.locator("a, button").filter(has_text=location).first
            await target.wait_for(state="visible", timeout=10000)
            await target.click()
            await page.wait_for_load_state("networkidle")
            steps.append({"label": f"③ 「{location}」クリック", "url": page.url, "ok": True})

            shot = await page.screenshot(type="png", full_page=False)
            screenshot = base64.b64encode(shot).decode()

        except Exception as e:
            steps.append({"label": "エラー発生", "url": page.url, "ok": False, "error": str(e)})
        finally:
            await browser.close()

    return {"steps": steps, "screenshot": screenshot}


@app.get("/", response_class=HTMLResponse)
async def index():
    account_count = len(ACCOUNTS)
    return f"""
<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>自動入力コントローラー</title>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: #f1f5f9; min-height: 100vh;
      display: flex; align-items: center; justify-content: center; padding: 20px;
    }}
    .card {{
      background: white; border-radius: 16px; padding: 40px 36px;
      width: 100%; max-width: 480px; box-shadow: 0 4px 24px rgba(0,0,0,0.08);
    }}
    h1 {{ font-size: 20px; font-weight: 700; color: #0f172a; margin-bottom: 4px; }}
    .sub {{ font-size: 13px; color: #94a3b8; margin-bottom: 28px; }}
    label {{ display: block; font-size: 13px; font-weight: 600; color: #475569; margin-bottom: 6px; }}
    input[type="text"] {{
      width: 100%; padding: 12px 14px;
      border: 1.5px solid #e2e8f0; border-radius: 10px;
      font-size: 15px; color: #0f172a; outline: none;
      transition: border-color 0.15s; margin-bottom: 20px;
    }}
    input[type="text"]:focus {{ border-color: #3b82f6; }}
    .btn-row {{ display: flex; gap: 10px; margin-top: 4px; }}
    button {{
      flex: 1; padding: 13px; border: none; border-radius: 10px;
      font-size: 14px; font-weight: 600; cursor: pointer;
      transition: background 0.15s, opacity 0.15s;
    }}
    button:disabled {{ opacity: 0.5; cursor: not-allowed; }}
    #btn-exec  {{ background: #2563eb; color: white; }}
    #btn-exec:hover:not(:disabled) {{ background: #1d4ed8; }}
    #btn-debug {{ background: #f1f5f9; color: #475569; border: 1.5px solid #e2e8f0; flex: 0 0 auto; width: 100px; }}
    #btn-debug:hover:not(:disabled) {{ background: #e2e8f0; }}
    #status {{
      margin-top: 20px; padding: 14px; border-radius: 10px;
      font-size: 14px; line-height: 1.7; display: none; white-space: pre-wrap;
    }}
    #status.running {{ background: #eff6ff; color: #1d4ed8; display: block; }}
    #status.success {{ background: #f0fdf4; color: #16a34a; display: block; }}
    #status.error   {{ background: #fef2f2; color: #dc2626; display: block; }}
    #debug-panel {{ margin-top: 20px; display: none; }}
    .step {{
      display: flex; align-items: flex-start; gap: 10px;
      padding: 10px 0; border-bottom: 1px solid #f1f5f9; font-size: 13px;
    }}
    .step-icon {{ font-size: 16px; flex-shrink: 0; margin-top: 1px; }}
    .step-label {{ font-weight: 600; color: #0f172a; }}
    .step-url {{ color: #64748b; font-size: 11px; word-break: break-all; margin-top: 2px; }}
    .step-error {{ color: #dc2626; font-size: 12px; margin-top: 2px; }}
    #debug-shot {{ margin-top: 14px; width: 100%; border-radius: 8px; border: 1px solid #e2e8f0; }}
  </style>
</head>
<body>
  <div class="card">
    <h1>自動入力コントローラー</h1>
    <p class="sub">アカウント {account_count} 件 接続済み</p>

    <label>場所</label>
    <input id="location" type="text" placeholder="ページ内に表示されているテキスト">

    <label>入力内容</label>
    <input id="value" type="text" placeholder="全アカウントに入力する文字列">

    <div class="btn-row">
      <button id="btn-exec"  onclick="execute()">全アカウントに実行</button>
      <button id="btn-debug" onclick="debugRun()">動作確認</button>
    </div>

    <div id="status"></div>
    <div id="debug-panel"></div>
  </div>

  <script>
    function setLoading(on) {{
      document.getElementById("btn-exec").disabled  = on;
      document.getElementById("btn-debug").disabled = on;
    }}

    async function execute() {{
      const location = document.getElementById("location").value.trim();
      const value    = document.getElementById("value").value.trim();
      const status   = document.getElementById("status");
      if (!location || !value) {{
        status.className = "error";
        status.textContent = "場所と入力内容を両方入力してください";
        return;
      }}
      setLoading(true);
      document.getElementById("debug-panel").style.display = "none";
      status.className = "running";
      status.textContent = "実行中... しばらくお待ちください";
      try {{
        const res  = await fetch("/execute", {{
          method: "POST", headers: {{ "Content-Type": "application/json" }},
          body: JSON.stringify({{ location, value }})
        }});
        const data = await res.json();
        const hasError = data.results.some(r => r.startsWith("❌"));
        status.className = hasError ? "error" : "success";
        status.textContent = data.results.join("\\n");
      }} catch (e) {{
        status.className = "error";
        status.textContent = "通信エラーが発生しました";
      }}
      setLoading(false);
    }}

    async function debugRun() {{
      const location = document.getElementById("location").value.trim();
      const status   = document.getElementById("status");
      const panel    = document.getElementById("debug-panel");
      if (!location) {{
        status.className = "error";
        status.textContent = "場所を入力してください";
        return;
      }}
      setLoading(true);
      panel.style.display = "none";
      status.className = "running";
      status.textContent = "動作確認中... ログイン→場所クリックまで実行します";
      try {{
        const res  = await fetch("/debug", {{
          method: "POST", headers: {{ "Content-Type": "application/json" }},
          body: JSON.stringify({{ location }})
        }});
        const data = await res.json();
        let html = "";
        for (const s of data.steps) {{
          html += `<div class="step">
            <span class="step-icon">${{s.ok ? "✅" : "❌"}}</span>
            <div>
              <div class="step-label">${{s.label}}</div>
              <div class="step-url">${{s.url}}</div>
              ${{s.error ? `<div class="step-error">${{s.error}}</div>` : ""}}
            </div>
          </div>`;
        }}
        if (data.screenshot) {{
          html += `<img id="debug-shot" src="data:image/png;base64,${{data.screenshot}}" alt="スクリーンショット">`;
        }}
        panel.innerHTML = html;
        panel.style.display = "block";
        const allOk = data.steps.every(s => s.ok);
        status.className = allOk ? "success" : "error";
        status.textContent = allOk
          ? "✅ ログイン・場所クリックまで成功。下のスクリーンショットで確認してください。"
          : "❌ どこかで止まりました。下の詳細を確認してください。";
      }} catch (e) {{
        status.className = "error";
        status.textContent = "通信エラーが発生しました";
      }}
      setLoading(false);
    }}
  </script>
</body>
</html>
"""


@app.post("/execute")
async def execute(req: InputRequest):
    if not ACCOUNTS:
        return {"results": ["❌ ACCOUNTS_JSON が未設定です。Railwayの Variables を確認してください。"]}
    results = await asyncio.gather(
        *[run_on_account(acc, req.location, req.value) for acc in ACCOUNTS]
    )
    return {"results": list(results)}


@app.post("/debug")
async def debug(req: DebugRequest):
    return await run_debug(req.location)
