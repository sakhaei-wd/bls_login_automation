# BLS Spain Global Login Flow Reproduction

This project reproduces the observed two-stage login flow for:

```text
https://turkey.blsspainglobal.com/Global/account/login
```

The goal is not to solve the image CAPTCHA. The implementation follows the assignment requirement: for Stage 2 it selects all 9 visible captcha images, submits a correctly shaped payload, and expects an HTTP 200 response with an invalid captcha selection result.

## What is implemented

### Stage 1

Observed request:

```text
POST /Global/account/LoginSubmit
Content-Type: application/x-www-form-urlencoded
```

Flow:

```text
GET /Global/account/login
  -> keep cookies in requests.Session
  -> parse __RequestVerificationToken
  -> parse dynamic input field names
  -> place the test email into the active dynamic e-mail field
  -> build ResponseData as JSON
POST /Global/account/LoginSubmit
  -> expect HTTP 200
  -> locate /Global/newcaptcha/logincaptcha?data=...
```

The captured request showed randomized field names such as `enivlb`, `pscjdsa`, `gmxbrrrv`, and a generated `ResponseData` JSON object. The code does not hardcode these names; it extracts them from the page.

### Stage 2

Observed request:

```text
POST /Global/NewCaptcha/LoginCaptchaSubmit
Content-Type: application/x-www-form-urlencoded
```

Flow:

```text
GET /Global/newcaptcha/logincaptcha?data=...
  -> parse __RequestVerificationToken
  -> parse Id, ReturnUrl, Param
  -> parse dynamic password fields
  -> parse visible captcha image ids from onclick="Select('image_id', this)"
  -> assume all 9 visible images are selected
  -> build SelectedImages=id1,id2,...,id9
  -> build ResponseData as JSON
POST /Global/NewCaptcha/LoginCaptchaSubmit
  -> expect HTTP 200 with invalid captcha selection
```

The captcha HTML contains many fake/hidden elements. The parser extracts CSS rules for `display:none`, `z-index`, `left`, and `top`, then selects the top-most visible image per grid cell.

## Project structure

```text
bls-login-automation/
├── main.py
├── requirements.txt
├── .env.example
├── README.md
├── pyproject.toml
├── bls_login_automation/
│   ├── client/session.py
│   ├── config.py
│   ├── constants.py
│   ├── parsers/login.py
│   ├── parsers/captcha.py
│   ├── models/payloads.py
│   └── utils/
└── tests/test_parsers.py
```

## Setup

Create a virtual environment:

```bash
python -m venv .venv
```

Activate it:

Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

macOS/Linux:

```bash
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Create your local `.env` file:

```bash
cp .env.example .env
```

Fill in:

```env
BLS_EMAIL=your_test_email@example.com
BLS_PASSWORD=your_test_password
BLS_PROXY_URL=http://username:password@host:port
```

Use one proxy for one complete login session. Do not rotate the proxy during a session because cookies and anti-forgery tokens may be tied to session state.

## Run

```bash
python main.py
```

Expected output shape:

```text
Stage 1 HTTP status: 200
Stage 2 HTTP status: 200
Stage 2 selected images count: 9
Stage 2 response preview: ... Invalid captcha selection ...
```

## Optional overrides

The site uses randomized field names and sometimes changes markup. The parser uses heuristics, but field names can be forced if needed:

```env
BLS_STAGE1_EMAIL_FIELD=gmxbrrrv
BLS_STAGE2_PASSWORD_FIELD=aocltamn
```

These should only be used for debugging. The preferred implementation path is dynamic extraction.

## Debugging

Enable HTML dumps:

```env
BLS_DEBUG_HTML=true
```

Then rerun:

```bash
python main.py
```

Debug files will be written under:

```text
debug/stage1_login_page.html
debug/stage1_response.html
debug/stage2_captcha_page.html
```

## Notes

- CAPTCHA solving is intentionally not implemented.
- The implementation demonstrates session handling, cookie preservation, anti-forgery token reuse, dynamic field extraction, and payload generation.
- The expected Stage 2 result is HTTP 200 with an invalid captcha selection response, because all 9 images are submitted by design.

## Stage 1 field auto-discovery

The login page uses obfuscated/random input names and may return HTTP 200 with a `/Login?err=...` URL when the e-mail is placed in the wrong dynamic field. The implementation ranks likely e-mail fields and, when no explicit `BLS_STAGE1_EMAIL_FIELD` is configured, retries candidates with a fresh GET/token until the captcha URL is reached. The successful field is printed as `Stage 1 selected e-mail field`.

For deterministic runs after a successful attempt, copy that printed field into `.env` as:

```env
BLS_STAGE1_EMAIL_FIELD=the_printed_field_name
```
