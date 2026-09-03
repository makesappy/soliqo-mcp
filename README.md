# Soliqo MCP Server

Connect your Soliqo account to AI assistants (Claude Desktop, Cursor, Cline, Kilo Code, and any other MCP client). Once connected, your assistant can process new recordings and work with your existing notes — the same capabilities you have in the Soliqo mobile app, straight from the chat.

## Getting access

Soliqo MCP is available to existing Soliqo app users.

1. Email **support@soliqo.online** and request an MCP API key.
2. You will receive a personal API key.
3. Treat the key like a password: anyone who has it can read and manage your notes. Store it in a secret manager, never commit it to git, and email support to revoke or rotate it at any time.

Your MCP usage shares the same plan limits as your Soliqo app account.

## Available tools

**Process new content**

| Tool | Description |
|---|---|
| `audio_process_file` | Upload a local audio file (meeting, lecture, interview) for transcription and summarization |
| `youtube_process` | Summarize a YouTube video by URL |
| `podcast_process` | Summarize a podcast episode by URL |
| `podcast_platforms` | List supported podcast platforms |

**Work with your notes**

| Tool | Description |
|---|---|
| `notes_list` | List your notes with pagination, optionally filtered by source (audio / youtube / pdf / podcast) |
| `notes_list_all` | List every note at once, without pagination |
| `note_get` | Full note detail: title, summary, transcript, language, edit state |
| `note_get_transcription` | The full transcript of a note |
| `note_edit_summary` | Edit a note's summary with a natural-language instruction (e.g. "make it shorter and add action items") |
| `note_reset_summary` | Restore the original AI-generated summary, discarding manual edits |
| `note_translate` | Translate a note's summary (en, uk, ru, cs, es, de, fr) |
| `pdf_process` | Upload a PDF for summarization |

**Task management**

| Tool | Description |
|---|---|
| `tasks_get_status` | Check the status/result of a task while it is processing |
| `tasks_get_pipeline` | Pipeline execution metadata for a task |
| `tasks_delete` | Delete a completed or failed task |

Note: `note_edit_summary` is asynchronous — the tool confirms the edit was accepted, and the updated summary appears in `note_get` after a short delay.

## Setup

Requirements: Python 3.10+

```bash
git clone <this repo> && cd soliqo-mcp
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

The server reads two environment variables:

| Variable | Required | Description |
|---|---|---|
| `SOLIQO_MCP_API_KEY` | yes | Your personal API key from support |

### Claude Desktop

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "soliqo": {
      "command": "/path/to/soliqo-mcp/.venv/bin/python",
      "args": ["/path/to/soliqo-mcp/server.py"],
      "env": {
        "SOLIQO_MCP_API_KEY": "your-key-here"
      }
    }
  }
}
```

### Cursor / other MCP clients

Use the same `command` / `args` / `env` values in your client's MCP server settings (stdio transport).

## Example prompts

- "Summarize this recording: ~/Downloads/standup.m4a"
- "What notes did I create this week? Give me a short list."
- "Show me the transcript of my latest meeting."
- "Rewrite the summary of <note> as bullet points with owners and deadlines."
- "Translate my latest lecture summary to German."

## Support

Questions, key revocation, or access issues: **support@soliqo.online**
