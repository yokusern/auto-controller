from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from playwright.async_api import async_playwright
import asyncio

app = FastAPI()

# =============================
# ここだけ書き換えてください
# =============================
LOGIN_URL  = "https://website.jp/login"   # ← ログインページのURL
MYPAGE_URL = "https://website.jp/MyPage"  # ← ログイン後のマイページURL

ACCOUNTS = [
    {"username": "account_a", "password": "pass_A"},
    {"username": "account_b", "password": "pass_B"},
    {"username": "account_c", "password": "pass_C"},
]
# =============================


class InputRequest(BaseModel):
    location: str  # 場所の名前（例: dott）
    value: str     # 入力する文字列


async def run_on_account(account: dict, location: str, value: str) -> str:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        try:
            # ── ① ログイン ──────────────────────────────
            await page.goto(LOGIN_URL)
            await page.wait_for_load_state("networkidle")

            # ID欄（input[type=text] or input[type=email] の最初の要素）
            await page.locator(
                "input[type='text'], input[type='email'], input[name*='id'], input[name*='user']"
            ).first.fill(account["username"])

            # パスワード欄
            await page.locator("input[type='password']").first.fill(account["password"])

            # ログインボタン
            await page.locator(
                "button[type='submit'], input[type='submit'], button:has-text('ログイン')"
            ).first.click()
            await page.wait_for_load_state("networkidle")

            # ── ② マイページへ移動 ────────────────────────
            await page.goto(MYPAGE_URL)
            await page.wait_for_load_state("networkidle")

            # ── ③ 場所をページ内検索してクリック ────────────
            # a・button のみを対象に完全一致で検索（ラベル誤クリック防止）
            target = page.locator(f"a, button").filter(has_text=location).first
            await target.wait_for(state="visible", timeout=10000)
            await target.click()
            await page.wait_for_load_state("networkidle")

            # ── ④ 入力欄を自動検出して入力 ──────────────────
            # ページに input か textarea が1つだけある前提
            field = page.locator("input:visible, textarea:visible").first
            await field.wait_for(state="visible", timeout=10000)
            await field.fill(value)

            # ── ⑤ 送信ボタンをクリック ────────────────────────
            # 「送信」テキストのボタンを優先、なければ type=submit にフォールバック
            submit_btn = page.get_by_role("button", name="送信")
            if await submit_btn.count() > 0:
                await submit_btn.first.click()
            else:
                await page.locator(
                    "button[type='submit'], input[type='submit']"
                ).first.click()
            await page.wait_for_load_state("networkidle")

            return f"✅ {account['username']} 完了"

        except Exception as e:
            return f"❌ {account['username']} エラー: {str(e)}"

        finally:
            await browser.close()


@app.get("/", response_class=HTMLResponse)
async def index():
    return """
<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>自動入力コントローラー</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: #f1f5f9;
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 20px;
    }

    .card {
      background: white;
      border-radius: 16px;
      padding: 40px 36px;
      width: 100%;
      max-width: 440px;
      box-shadow: 0 4px 24px rgba(0,0,0,0.08);
    }

    h1 {
      font-size: 20px;
      font-weight: 700;
      color: #0f172a;
      margin-bottom: 32px;
    }

    label {
      display: block;
      font-size: 13px;
      font-weight: 600;
      color: #475569;
      margin-bottom: 6px;
    }

    input[type="text"] {
      width: 100%;
      padding: 12px 14px;
      border: 1.5px solid #e2e8f0;
      border-radius: 10px;
      font-size: 15px;
      color: #0f172a;
      outline: none;
      transition: border-color 0.15s;
      margin-bottom: 20px;
    }

    input[type="text"]:focus {
      border-color: #3b82f6;
    }

    button {
      width: 100%;
      padding: 13px;
      background: #2563eb;
      color: white;
      border: none;
      border-radius: 10px;
      font-size: 15px;
      font-weight: 600;
      cursor: pointer;
      transition: background 0.15s, opacity 0.15s;
      margin-top: 4px;
    }

    button:hover:not(:disabled) { background: #1d4ed8; }
    button:disabled { opacity: 0.5; cursor: not-allowed; }

    #status {
      margin-top: 20px;
      padding: 14px;
      border-radius: 10px;
      font-size: 14px;
      line-height: 1.7;
      display: none;
      white-space: pre-wrap;
    }

    #status.running  { background: #eff6ff; color: #1d4ed8; display: block; }
    #status.success  { background: #f0fdf4; color: #16a34a; display: block; }
    #status.error    { background: #fef2f2; color: #dc2626; display: block; }
  </style>
</head>
<body>
  <div class="card">
    <h1>自動入力コントローラー</h1>

    <label>場所（ページ内に表示されている文字で検索）</label>
    <input id="location" type="text" placeholder="例: dott">

    <label>入力内容</label>
    <input id="value" type="text" placeholder="ここに入力する文字列">

    <button id="btn" onclick="execute()">全アカウントに実行</button>

    <div id="status"></div>
  </div>

  <script>
    async function execute() {
      const location = document.getElementById("location").value.trim();
      const value    = document.getElementById("value").value.trim();
      const status   = document.getElementById("status");
      const btn      = document.getElementById("btn");

      if (!location || !value) {
        status.className = "error";
        status.textContent = "場所と入力内容を両方入力してください";
        return;
      }

      btn.disabled = true;
      status.className = "running";
      status.textContent = "実行中... しばらくお待ちください";

      try {
        const res = await fetch("/execute", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ location, value })
        });
        const data = await res.json();

        const hasError = data.results.some(r => r.startsWith("❌"));
        status.className = hasError ? "error" : "success";
        status.textContent = data.results.join("\n");
      } catch (e) {
        status.className = "error";
        status.textContent = "通信エラーが発生しました";
      }

      btn.disabled = false;
    }
  </script>
</body>
</html>
"""


@app.post("/execute")
async def execute(req: InputRequest):
    results = await asyncio.gather(
        *[run_on_account(acc, req.location, req.value) for acc in ACCOUNTS]
    )
    return {"results": list(results)}
