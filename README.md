# agente-email

Dockerized, headless email + calendar agent:

- Reads email via IMAP
- Classifies and files mail into folders (MOVE)
- Creates reply drafts in IMAP Drafts (never sends)
- Creates Google Calendar events for validated requests
- Creates TODO calendar events for explicit deadline requests
- Generates a daily “Executive Brief” as a draft email
- Sends daily/weekly recaps and a reply-cleanup digest (appends to Sent)
- Automatically clears replied threads from the ToReply folder by scanning Sent

## Quick start

1) Create your configuration file:
   ```bash
   cp .env.example .env
   ```
   Edit `.env` to set your credentials (see **Configuration** below).

2) Start the service:

```bash
docker compose up -d
docker compose logs -f agent
```

State is persisted in `./data/agent_state.db` and Google OAuth tokens in `./data/google_token.json`.

## Configuration

Required IMAP:

- `IMAP_HOST`, `IMAP_PORT` (default `993`)
- `IMAP_USERNAME`, `IMAP_PASSWORD`

- Recommended:

- `IMAP_FOLDER_INBOX` (default `INBOX`) – this is the folder the agent polls for new messages.
- `IMAP_MAILBOX_PREFIX` (optional; `INBOX.` or `INBOX/`) – only set this when your server requires every mailbox to sit under
  an `INBOX` namespace (e.g., `INBOX.CalendarCreated`). The agent automatically prepends it when creating/moving folders.
- `IMAP_DRAFTS_FOLDER` (default `Drafts`)
- `IMAP_CREATE_FOLDERS_ON_STARTUP` (default `true`)
- `IMAP_FILING_MODE` (`move` or `copy`, default `move`)
- `IMAP_CLASSIFICATION_FOLDERS_JSON` (optional JSON mapping; defaults provided in code)
- `VIP_SENDERS_JSON` (optional JSON list of emails/domains)

LLM (OpenRouter):

- `OPENROUTER_API_KEY`
- `OPENROUTER_MODEL`
- `OPENROUTER_BASE_URL` (default `https://openrouter.ai/api/v1`)

Google Calendar:

- `GOOGLE_OAUTH_CLIENT_SECRET_JSON` (host path, required for setup only)
- `GOOGLE_CALENDAR_ID` (default `primary`)
- `TZ` (timezone, e.g. `Europe/Rome`)

Executive Brief:

- `EXECUTIVE_BRIEF_ENABLED` (default `true`)
- `EXECUTIVE_BRIEF_TIME_LOCAL` (default `07:30`)
- `EXECUTIVE_BRIEF_LOOKBACK_HOURS` (default `24`)
- `EXECUTIVE_BRIEF_TO` (default `IMAP_USERNAME`)
- `EXECUTIVE_BRIEF_SUBJECT_PREFIX` (default `[Executive Brief]`)

Daily Recap:

- `DAILY_RECAP_ENABLED` (default `true`)
- `DAILY_RECAP_TIME_LOCAL` (default `18:00`)
- `DAILY_RECAP_LOOKBACK_HOURS` (default `24`)
- `DAILY_RECAP_TO` (default `IMAP_USERNAME`)
- `DAILY_RECAP_SUBJECT_PREFIX` (default `[Daily Recap]`)

Weekly Recap:

- `WEEKLY_RECAP_ENABLED` (default `true`)
- `WEEKLY_RECAP_DAY_LOCAL` (default `Mon`)
- `WEEKLY_RECAP_TIME_LOCAL` (default `08:00`)
- `WEEKLY_RECAP_LOOKBACK_DAYS` (default `7`)
- `WEEKLY_RECAP_TO` (default `IMAP_USERNAME`)
- `WEEKLY_RECAP_SUBJECT_PREFIX` (default `[Weekly Recap]`)

Reply Digest:

- `REPLIED_DIGEST_ENABLED` (default `true`)
- `REPLIED_DIGEST_INTERVAL_MINUTES` (default `60`) – how often to send the digest (hourly by default).
- `REPLIED_DIGEST_LOOKBACK_MINUTES` (default `60`) – which window to summarize (to avoid duplicate entries).
- `REPLIED_DIGEST_TIME_LOCAL` (legacy; no longer used for scheduling)
- `REPLIED_DIGEST_TO` (default `IMAP_USERNAME`)
- `REPLIED_DIGEST_SUBJECT_PREFIX` (default `[Reply Digest]`)

Reply Reconciliation:

- `IMAP_SENT_FOLDER` (required to auto-clear replied items)
- `IMAP_REPLIED_FOLDER` (default `Replied`)

## One-time Google OAuth

You need a Google OAuth “client secret” JSON once, then you run an auth helper once to generate a refresh token
stored in `./data/google_token.json`.

### 1) Create the Google OAuth client secret JSON

1) Go to Google Cloud Console → create/select a project.
2) APIs & Services → Library → enable **Google Calendar API**.
3) APIs & Services → OAuth consent screen:
   - Choose **External** (typical) and fill required fields.
   - Add your Google account under **Test users** (if the app is in testing).
4) APIs & Services → Credentials → **Create credentials** → **OAuth client ID**:
   - Application type: **Desktop app** (recommended for this local flow).
   - Download the JSON and save it locally (e.g., as `./secrets/google_client.json`).

### 2) Run the Auth Helper

1) In your `.env`, set `GOOGLE_OAUTH_CLIENT_SECRET_JSON` to the **absolute path** of your downloaded JSON file.
   ```bash
   GOOGLE_OAUTH_CLIENT_SECRET_JSON=/home/user/projects/agente-email/secrets/google_client.json
   ```

2) Run the auth helper service:
   ```bash
   docker compose --profile auth run --rm --service-ports auth-google
   ```

3) Follow the link printed in the terminal, authenticate with Google, and copy the code back if requested (or it might handle the redirect if ports are mapped).
   - The helper will write the token to `./data/google_token.json`.

### 3) Configure the agent to use Calendar

In your `.env`:

- Set `TZ` (e.g. `Europe/Rome`) to resolve ambiguous times.
- Optionally set `GOOGLE_CALENDAR_ID` (default `primary`).

If `./data/google_token.json` is missing or invalid, calendar actions are skipped/errored while email drafting
continues.

### Troubleshooting

- If you see `Error 400: invalid_request` / `redirect_uri_mismatch`: ensure you created a **Desktop app** OAuth
  client. If you used a **Web application** client, add `http://localhost:8080/` to **Authorized redirect URIs**.
- If the error mentions `redirect_uri=http://0.0.0.0:8080/`, rebuild and re-run the helper so it prints a fresh URL:
  `docker compose --profile auth run --rm --service-ports --build auth-google` (the redirect must be `localhost`).
- If you see an “app not verified / access blocked” message: make sure the OAuth consent screen is configured and
  your account is added under **Test users** (when in testing mode).
- If the agent crashes with `socket.gaierror: Name or service not known`: your `IMAP_HOST` is not resolvable.
  Verify locally with `getent hosts $IMAP_HOST` and fix `.env` (common typo: `.com` vs `.it` for some providers).
- If you see `Client tried to access nonexistent namespace ... (Mailbox name should probably be prefixed with: INBOX.)`:
  set `IMAP_MAILBOX_PREFIX=INBOX.` in `.env` (or use `INBOX/` depending on your server).

## Development

```bash
python -m pip install -e '.[dev]'
ruff check .
ruff format --check .
pytest
mypy src
```

## Workflow (scheme)

```mermaid
flowchart TB
  subgraph pollLoop [PollLoop]
    Poll[PollIMAP INBOX] --> Fetch[FetchRFC822+Flags]
    Fetch --> Parse[ParseEmail to meta+text]
    Parse --> Graph[LangGraphInvoke]
  end

  subgraph graphNodes [LangGraphNodes]
    Graph --> Priority[priority_score]
    Priority --> Classify[classify_email (LLM)]
    Classify --> Decide[decide_actions]
    Decide --> Draft[draft_reply (LLM)]
    Draft --> Extract[extract_event (LLM)]
    Extract --> Validate[validate_event]
    Validate --> Create[create_calendar_event]
    Create --> File[file_email (MOVE/COPY)]
    File --> Persist[persist_state]
  end

  subgraph scheduled [ScheduledTasks]
    Brief[ExecutiveBrief] --> Drafts[Append to Drafts]
    Daily[DailyRecap] --> Sent1[Append to Sent]
    Weekly[WeeklyRecap] --> Sent2[Append to Sent]
    HourlyDigest[ReplyDigest hourly] --> Sent3[Append to Sent]
    Reconcile[ReconcileReplied] --> MoveToReplied[Move ToReply to Replied]
  end
```
