# Second Shift: account setup (all free)

Do these while the code gets built. About 20 minutes total.
Put secrets in files on disk. Don't paste keys into chat.

First: `cp .env.example .env` (in this folder).

---

## 1. Google (Sheets + Calendar + Gmail). Free, no billing needed. ~10 min

Use a **personal** Google account, not a work one. A fresh throwaway Gmail is ideal.

1. Go to https://console.cloud.google.com/ and sign in with that account.
2. Top bar project picker: **New project**. Name it `second-shift`. Select it.
3. Menu: **APIs & Services > Library**. Search and **Enable** each one:
   - Google Sheets API
   - Google Calendar API
   - Gmail API
4. Menu: **APIs & Services > OAuth consent screen** (may be called **Google Auth Platform**). Click **Get started**.
   - App name: `Second Shift`. Support email: your address.
   - Audience: **External**.
   - Contact email: your address. Finish.
5. Still in Google Auth Platform: **Audience** tab. Under **Test users**, click **Add users** and add your own Gmail address.
6. **Clients** tab: **Create client**.
   - Application type: **Desktop app**. Name: `second-shift-local`.
   - Click **Download JSON**.
   - Save it in this project as: `secrets/google_oauth_client.json`
     (create the `secrets` folder if it doesn't exist).
7. In `.env`, set `DEMO_GMAIL=` to that Gmail address.

Later, the first time the app runs, a browser window asks you to approve access.
Google will warn "Google hasn't verified this app". That's expected for a test app:
click **Advanced > Go to Second Shift (unsafe)**, then allow.

---

## 2. Slack. Free. ~5 min

1. Create a new free workspace at https://slack.com/get-started#/createnew
   (name it something like `second-shift-demo`).
2. In that workspace, create a public channel named `#dispatch`.
3. Go to https://api.slack.com/apps > **Create New App** > **From a manifest**.
   - Pick the new workspace.
   - Choose **YAML** and paste the contents of `slack-app-manifest.yaml` from this folder.
   - Create.
4. Left menu: **Install App** > **Install to Workspace** > Allow.
5. Copy the **Bot User OAuth Token** (starts with `xoxb-`) into `.env` as `SLACK_BOT_TOKEN=`.
6. In Slack, open `#dispatch` and type `/invite @Second Shift`.

---

## 3. Anthropic API key. ~2 min

This is the only piece that isn't free. It's pay-as-you-go, and we only make a few short calls per run.

1. https://console.anthropic.com/ > **API Keys** > **Create key**.
2. Put it in `.env` as `ANTHROPIC_API_KEY=`.

---

## 4. Tell Claude "setup done"

Claude then runs `scripts/check_setup.py`, which checks each connection and reports what's missing.

---

## Not needed (skipped to stay free)

- **Arga twins.** The free plan allows 1 twin at a time for 10 minutes. We test against our own built-in fake apps instead, and run a live check against the real accounts.
- **Lemma.** No free tier found. The app records its own step-by-step trace instead.
